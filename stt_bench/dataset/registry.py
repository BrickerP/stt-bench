"""Dataset registry wrapper."""

from stt_bench.dataset import loader
from stt_bench.settings import Settings


class DatasetRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings

    def list_datasets(self):
        return loader.list_datasets(self.settings)

    def load(self, dataset_id: str = "default"):
        return loader.load_manifest(self.settings, dataset_id)

    def validate(self, dataset_id: str = "default"):
        return loader.validate_dataset(self.settings, dataset_id)

    def stats(self, dataset_id: str = "default"):
        return loader.get_dataset_stats(self.settings, dataset_id)

    def get_sample(self, dataset_id: str, sample_id: str):
        return loader.get_sample(dataset_id, sample_id, self.settings)

    def resolve_path(self, sample):
        return loader.resolve_audio_path(sample, self.settings)
