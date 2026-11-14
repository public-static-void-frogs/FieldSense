from model import TempCNN

import torch
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader
from sklearn.model_selection import train_test_split
import numpy as np
import json
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix
import os


def plot_learning_curves(train_losses, val_losses, train_accs, val_accs):
    epochs = range(1, len(train_losses) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    axes[0].plot(epochs, train_losses, 'b-', label='Train Loss', linewidth=2)
    axes[0].plot(epochs, val_losses, 'r-', label='Validation Loss', linewidth=2)
    axes[0].set_title('Loss function plot', fontsize=14)
    axes[0].set_xlabel('Epoch', fontsize=12)
    axes[0].set_ylabel('Loss', fontsize=12)
    axes[0].legend(fontsize=12)
    axes[0].grid(True, linestyle='--', alpha=0.7)

    axes[1].plot(epochs, train_accs, 'b-', label='Train Accuracy', linewidth=2)
    axes[1].plot(epochs, val_accs, 'r-', label='Validation Accuracy', linewidth=2)
    axes[1].set_title('Accuracy function plot', fontsize=14)
    axes[1].set_xlabel('Epoch', fontsize=12)
    axes[1].set_ylabel('Accuracy', fontsize=12)
    axes[1].legend(fontsize=12)
    axes[1].grid(True, linestyle='--', alpha=0.7)

    plt.tight_layout()
    plt.show()

def plot_confusion_matrix(y_true, y_pred, class_names):
    cm = confusion_matrix(y_true, y_pred)
    cm_normalized = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]

    plt.figure(figsize=(8, 6))
    sns.heatmap(cm_normalized, annot=True, fmt=".2f", cmap="Blues",
                xticklabels=class_names, yticklabels=class_names,
                cbar_kws={'label': 'Proportion of correct answers'})

    plt.title('Confusion Matrix', fontsize=14)
    plt.ylabel('True Class', fontsize=12)
    plt.xlabel('Predicted Class', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.yticks(rotation=0)

    plt.tight_layout()
    plt.show()

X_numpy = np.load('X.npy')
y_numpy = np.load('y.npy')

with open('classes.json', 'r', encoding='utf-8') as f:
    classes_dict = json.load(f)
NUM_CLASSES = len(classes_dict)

print(f"Download fields: {X_numpy.shape[0]}, Classes: {NUM_CLASSES}")

if X_numpy.shape[1] == 16 and X_numpy.shape[2] == 3:
    X_numpy = np.transpose(X_numpy, (0, 2, 1))


X_tensor = torch.tensor(X_numpy, dtype=torch.float32)
y_tensor = torch.tensor(y_numpy, dtype=torch.long)

X_temp, X_test, y_temp, y_test = train_test_split(
    X_tensor, y_tensor, test_size=0.10, random_state=42, stratify=y_tensor
)
X_train, X_val, y_train, y_val = train_test_split(
    X_temp, y_temp, test_size=1/9, random_state=42, stratify=y_temp
)

BATCH_SIZE = 64
train_loader = DataLoader(TensorDataset(X_train, y_train), batch_size=BATCH_SIZE, shuffle=True)
val_loader = DataLoader(TensorDataset(X_val, y_val), batch_size=BATCH_SIZE, shuffle=False)
test_loader = DataLoader(TensorDataset(X_test, y_test), batch_size=BATCH_SIZE, shuffle=False)


device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = TempCNN(input_channels=3, num_classes=NUM_CLASSES).to(device)

criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.0001)
scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=3)


if os.path.exists('tempcnn_best.pth'):
    print("\n[!] File tempcnn_best.pth found. Loading knowledge to continue training...")
    model.load_state_dict(torch.load('tempcnn_best.pth', weights_only=True))
else:
    print("\n[!] Weights file not found. Starting training from scratch...")


EPOCHS = 40
best_val_loss = float('inf')

train_loss_hist = []
val_loss_hist = []
train_acc_hist = []
val_acc_hist = []

print("\nStart training...")
for epoch in range(EPOCHS):
    model.train()
    train_loss, correct_train, total_train = 0.0, 0, 0
    for inputs, labels in train_loader:
        inputs, labels = inputs.to(device), labels.to(device)

        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        train_loss += loss.item()
        predicted = torch.argmax(outputs, dim=1)
        total_train += labels.size(0)
        correct_train += (predicted == labels).sum().item()

    avg_train_loss = train_loss / len(train_loader)
    train_acc = correct_train / total_train


    model.eval()
    val_loss, correct_val, total_val = 0.0, 0, 0
    with torch.no_grad():
        for inputs, labels in val_loader:
            inputs, labels = inputs.to(device), labels.to(device)
            outputs = model(inputs)
            loss = criterion(outputs, labels)

            val_loss += loss.item()
            predicted = torch.argmax(outputs, dim=1)
            total_val += labels.size(0)
            correct_val += (predicted == labels).sum().item()

    avg_val_loss = val_loss / len(val_loader)
    val_acc = correct_val / total_val

    scheduler.step(avg_val_loss)

    train_loss_hist.append(avg_train_loss)
    val_loss_hist.append(avg_val_loss)
    train_acc_hist.append(train_acc)
    val_acc_hist.append(val_acc)

    print(f"Epoch {epoch+1:02d} | Train Acc: {train_acc:.4f} | Val Acc: {val_acc:.4f} | Val Loss: {avg_val_loss:.4f}")

    if avg_val_loss < best_val_loss:
        best_val_loss = avg_val_loss
        torch.save(model.state_dict(), 'tempcnn_best.pth')
        print("\nSave tempcnn_best.pth")

plot_learning_curves(train_loss_hist, val_loss_hist, train_acc_hist, val_acc_hist)



model.load_state_dict(torch.load('tempcnn_best.pth', weights_only=True))
model.eval()

test_correct = 0
all_true = []
all_preds = []

with torch.no_grad():
    for inputs, labels in test_loader:
        inputs, labels = inputs.to(device), labels.to(device)

        outputs = model(inputs)
        predicted = torch.argmax(outputs, dim=1)

        test_correct += (predicted == labels).sum().item()
        all_true.extend(labels.cpu().numpy())
        all_preds.extend(predicted.cpu().numpy())

test_accuracy = test_correct / len(y_test)
print(f"\nTest Acc: {test_accuracy:.4f} ({test_accuracy * 100:.2f}%)")

class_names = list(classes_dict.keys())
plot_confusion_matrix(all_true, all_preds, class_names)