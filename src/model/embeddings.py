from sentence_transformers import SentenceTransformer
import numpy as np

class MergenEmbedder:
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        """
        Turkce dil destegi olan cok dilli embedding modelini yukler.
        """
        # Cok dilli (multilingual) model secimi Turkce NLP kalitesi icin kritiktir.
        self.model = SentenceTransformer(model_name)

    def create_embeddings(self, texts: list) -> np.ndarray:
        """
        Metin listesini vektorlere (embedding) cevirir.
        """
        return self.model.encode(texts, show_progress_bar=True)