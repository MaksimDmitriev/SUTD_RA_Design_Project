from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image


PROMPTS = {
    "trash": [
        "a photo of a tissue on the floor",
        "a photo of a paper scrap on the floor",
        "a photo of a plastic wrapper on the floor",
        "a photo of rubbish on the floor",
    ],
    "keep": [
        "a photo of a sock on the floor",
        "a photo of a small piece of clothing on the floor",
        "a photo of a plush toy on the floor",
        "a photo of a useful object on the floor",
    ],
    "ignore": [
        "a photo of a cable on the floor",
        "a photo of a heavy object on the floor",
        "a photo of an unknown object on the floor",
        "a photo of floor with no relevant object",
    ],
}


@dataclass
class Prediction:
    label: str
    confidence: float
    prompt: str
    scores: dict[str, float]


class ClipClassifier:
    def __init__(
        self,
        model_name: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
    ):
        self.model_name = model_name
        self.pretrained = pretrained
        self._ready = False
        self._load_error: str | None = None
        self._torch: Any = None
        self._open_clip: Any = None
        self._model: Any = None
        self._preprocess: Any = None
        self._text_features: Any = None
        self._flat_prompts: list[tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return self._ready

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def load(self) -> None:
        if self._ready:
            return

        try:
            import torch
            import open_clip

            self._torch = torch
            self._open_clip = open_clip
            self._model, _, self._preprocess = open_clip.create_model_and_transforms(
                self.model_name,
                pretrained=self.pretrained,
                device="cpu",
            )
            self._model.eval()
            tokenizer = open_clip.get_tokenizer(self.model_name)

            self._flat_prompts = [
                (label, prompt)
                for label, prompts in PROMPTS.items()
                for prompt in prompts
            ]
            text = tokenizer([prompt for _, prompt in self._flat_prompts])

            with torch.no_grad():
                self._text_features = self._model.encode_text(text)
                self._text_features /= self._text_features.norm(dim=-1, keepdim=True)

            self._ready = True
            self._load_error = None
        except Exception as exc:
            self._load_error = str(exc)
            raise

    def predict(self, frame_bgr: np.ndarray) -> Prediction:
        self.load()

        torch = self._torch
        image_rgb = frame_bgr[:, :, ::-1]
        image = Image.fromarray(image_rgb)
        image_tensor = self._preprocess(image).unsqueeze(0)

        with torch.no_grad():
            image_features = self._model.encode_image(image_tensor)
            image_features /= image_features.norm(dim=-1, keepdim=True)
            prompt_probs = (100.0 * image_features @ self._text_features.T).softmax(dim=-1)[0]

        grouped: dict[str, float] = {label: 0.0 for label in PROMPTS}
        best_prompt = ""
        best_prompt_score = -1.0

        for idx, (label, prompt) in enumerate(self._flat_prompts):
            score = float(prompt_probs[idx].item())
            grouped[label] += score
            if score > best_prompt_score:
                best_prompt_score = score
                best_prompt = prompt

        label = max(grouped, key=grouped.get)
        return Prediction(
            label=label,
            confidence=grouped[label],
            prompt=best_prompt,
            scores=grouped,
        )
