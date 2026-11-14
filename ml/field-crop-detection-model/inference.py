import torch
import numpy as np
import json
import os
from model import TempCNN

class CropPredictor:
    def __init__(self, model_path='weights/tempcnn_best.pth', classes_path='../../data/classes.json'):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        with open(classes_path, 'r', encoding='utf-8') as f:
            self.classes_dict = json.load(f)
        
        self.class_names = list(self.classes_dict.keys())
        self.num_classes = len(self.class_names)
        
        self.model = TempCNN(input_channels=3, num_classes=self.num_classes).to(self.device)
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Weights file not found: {model_path}")
            
        self.model.load_state_dict(torch.load(model_path, map_location=self.device, weights_only=True))
        self.model.eval()

    def predict(self, field_data):
        if field_data.shape == (16, 3):
            field_data = np.transpose(field_data, (1, 0))
            
        if len(field_data.shape) == 2:
            field_data = np.expand_dims(field_data, axis=0)

        tensor_data = torch.tensor(field_data, dtype=torch.float32).to(self.device)

        with torch.no_grad():
            outputs = self.model(tensor_data)
            probabilities = torch.nn.functional.softmax(outputs, dim=1)[0]
            predicted_idx = torch.argmax(outputs, dim=1).item()

        predicted_crop = self.class_names[predicted_idx]
        probs_dict = {self.class_names[i]: float(prob) for i, prob in enumerate(probabilities)}

        return predicted_crop, probs_dict