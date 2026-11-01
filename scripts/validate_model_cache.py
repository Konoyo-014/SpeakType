import json
from pathlib import Path
import tempfile
from unittest import TestCase

import numpy as np
from safetensors import safe_open
from safetensors.numpy import save_file

from speaktype.model_download import model_snapshot_is_complete


work = Path(__file__).resolve().parents[1] / "work"
work.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=work, prefix="model-cache-") as directory:
    snapshot = Path(directory)
    assert not model_snapshot_is_complete(snapshot)
    for name in ("config.json", "tokenizer_config.json", "preprocessor_config.json", "tokenizer.json"):
        (snapshot / name).write_text('{"validation": true}', encoding="utf-8")
    assert not model_snapshot_is_complete(snapshot)
    array = np.arange(128, dtype=np.float32)
    index = {"metadata": {"total_size": array.nbytes}, "weight_map": {"weights": "model.safetensors"}}
    index_path = snapshot / "model.safetensors.index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    assert not model_snapshot_is_complete(snapshot)
    shard = snapshot / "model.safetensors"
    shard.touch()
    assert not model_snapshot_is_complete(snapshot)
    save_file({"weights": array}, shard)
    assert model_snapshot_is_complete(snapshot)
    with safe_open(shard, framework="np") as data:
        assert np.array_equal(data.get_tensor("weights"), array)
    valid_bytes = shard.read_bytes()
    shard.write_bytes(valid_bytes[:32])
    assert not model_snapshot_is_complete(snapshot)
    shard.write_bytes(valid_bytes)
    (snapshot / "preprocessor_config.json").unlink()
    assert not model_snapshot_is_complete(snapshot)
    (snapshot / "preprocessor_config.json").write_text('{"feature_size": 128}', encoding="utf-8")
    index["weight_map"]["other"] = "missing-shard.safetensors"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    assert not model_snapshot_is_complete(snapshot)
    save_file({"other": array}, snapshot / "missing-shard.safetensors")
    assert model_snapshot_is_complete(snapshot)
    index["weight_map"]["does_not_exist"] = "model.safetensors"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    with TestCase().assertRaises(ValueError):
        model_snapshot_is_complete(snapshot)
    index_path.unlink()
    assert model_snapshot_is_complete(snapshot)
    config = snapshot / "config.json"
    config.write_text("", encoding="utf-8")
    assert not model_snapshot_is_complete(snapshot)
    config.write_text("invalid-json", encoding="utf-8")
    with TestCase().assertRaises(json.JSONDecodeError):
        model_snapshot_is_complete(snapshot)
print("Model cache verified with real safetensors files: absent, empty, truncated, missing shards/processors, complete and unsharded snapshots.")
