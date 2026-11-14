import os
import urllib.request
import torch
import cv2
import numpy as np
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

class FieldSegmenter:
    def __init__(self, checkpoint_path='weights/sam2_hiera_tiny.pt', config_name="sam2_hiera_t.yaml"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        if not os.path.exists(checkpoint_path):
            print(f"Downloading SAM 2 weights to {checkpoint_path}...")
            os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
            url = "https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_tiny.pt"
            urllib.request.urlretrieve(url, checkpoint_path)
            print("Download complete.")
            
        self.sam2_model = build_sam2(config_name, checkpoint_path, device=self.device)
        self.predictor = SAM2ImagePredictor(self.sam2_model)

    def segment_by_point(self, image_path, point_coords, point_label=1):

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        image = cv2.imread(image_path)
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        self.predictor.set_image(image_rgb)

        input_point = np.array([point_coords])
        input_label = np.array([point_label])

        masks, scores, logits = self.predictor.predict(
            point_coords=input_point,
            point_labels=input_label,
            multimask_output=False,
        )

        return masks[0], scores[0]