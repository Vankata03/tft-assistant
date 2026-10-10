"""Offline CPU fine-tuning from the pinned reader's actual ONNX parameters."""

import json
import shutil
import tempfile
from pathlib import Path


def fine_tune(
    current,
    split_path,
    output,
    *,
    epochs=3,
    batch_size=8,
    learning_rate=0.0001,
    seed=38,
):
    # Training dependencies never enter the live capture import path.
    import cv2
    import numpy as np
    import onnx
    import torch
    from onnx import numpy_helper
    from torch import nn
    from torchvision.models import efficientnet_b0

    from tft_capture._coach import preprocess
    from tft_capture.board_reader import CPUClassifier
    from tft_capture.model_validation import load_split
    from tft_capture.reader_assets import atomic_json

    current, split_path, output = Path(current), Path(split_path), Path(output)
    if epochs < 1 or batch_size < 1 or learning_rate <= 0:
        raise ValueError("Epochs, batch size and learning rate must be positive")
    if output.exists():
        raise ValueError(
            "Candidate directory already exists; use a new version directory"
        )
    split = load_split(split_path)
    metadata = json.loads((current / "unit_classifier.json").read_text())
    if metadata.get("architecture") != "efficientnet_b0":
        raise ValueError("Fine-tuning supports the pinned EfficientNet-B0 unit model")
    reference = CPUClassifier(
        current, "unit_classifier", set_number=metadata["set_number"]
    )
    labels = metadata["labels"]

    def target(label):
        matches = [
            index
            for index, name in enumerate(labels)
            if "".join(c for c in name.casefold() if c.isalnum())
            == "".join(c for c in label.casefold() if c.isalnum())
        ]
        if len(matches) != 1:
            raise ValueError(f"Training label {label} has no unique current class")
        return matches[0]

    targets = [target(row["label"]) for row in split["train"]]
    torch.set_num_threads(4)
    torch.manual_seed(seed)
    model = efficientnet_b0(weights=None, num_classes=len(labels)).cpu()
    # Upstream exported folded BatchNorm. Preserve that exact graph rather than loading random BN.
    for name, module in list(model.named_modules()):
        if isinstance(module, nn.BatchNorm2d):
            parent, _, leaf = name.rpartition(".")
            model.get_submodule(parent)._modules[leaf] = nn.Identity()
    graph = onnx.load(current / "unit_classifier.onnx", load_external_data=True)
    arrays = {
        value.name: numpy_helper.to_array(value).copy()
        for value in graph.graph.initializer
    }
    conv_nodes = {
        node.input[1]: node for node in graph.graph.node if node.op_type == "Conv"
    }
    for name, module in model.named_modules():
        key = name + ".weight"
        if isinstance(module, nn.Conv2d):
            node = conv_nodes.get(key)
            if node is None or len(node.input) != 3:
                raise ValueError(f"Unsupported current ONNX convolution: {key}")
            module.weight = nn.Parameter(torch.from_numpy(arrays[key]))
            module.bias = nn.Parameter(torch.from_numpy(arrays[node.input[2]]))
        elif isinstance(module, nn.Linear):
            module.weight = nn.Parameter(torch.from_numpy(arrays[key]))
            module.bias = nn.Parameter(torch.from_numpy(arrays[name + ".bias"]))

    def batch(rows):
        images = [
            cv2.imread(str(split_path.parent / row["file"]), cv2.IMREAD_COLOR)
            for row in rows
        ]
        if any(image is None for image in images):
            raise ValueError("Training crop cannot be decoded")
        return preprocess(images, metadata)

    sample = batch(split["train"][:batch_size])
    model.eval()
    with torch.no_grad():
        restored = model(torch.from_numpy(sample)).numpy()
    original = reference.session.run(
        None, {reference.session.get_inputs()[0].name: sample}
    )[0]
    error = float(np.max(np.abs(restored - original)))
    if error > 0.0001:
        raise ValueError(f"Current model reconstruction failed parity ({error})")
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    loss_fn = nn.CrossEntropyLoss()
    losses = []
    generator = torch.Generator().manual_seed(seed)
    for _ in range(epochs):
        model.train()
        order = torch.randperm(len(targets), generator=generator).tolist()
        total = 0.0
        for start in range(0, len(order), batch_size):
            indices = order[start : start + batch_size]
            inputs = torch.from_numpy(
                batch([split["train"][index] for index in indices])
            )
            optimizer.zero_grad()
            loss = loss_fn(
                model(inputs), torch.tensor([targets[index] for index in indices])
            )
            loss.backward()
            optimizer.step()
            total += float(loss.detach()) * len(indices)
        losses.append(total / len(targets))
    model.eval()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish the candidate only after export, parity and complete companion assets succeed.
    with tempfile.TemporaryDirectory(
        prefix=".reader-candidate-", dir=output.parent
    ) as temporary:
        staging = Path(temporary)
        path = staging / "unit_classifier.onnx"
        torch.onnx.export(
            model,
            torch.from_numpy(sample),
            str(path),
            dynamo=False,
            input_names=["image"],
            output_names=["logits"],
            opset_version=18,
            dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}},
            external_data=False,
        )
        exported = onnx.load(path)
        onnx.save_model(
            exported,
            path,
            save_as_external_data=True,
            all_tensors_to_one_file=True,
            location="unit_classifier.onnx.data",
            size_threshold=0,
        )
        metadata["training"] = {
            "device": "cpu",
            "epochs": epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "seed": seed,
            "losses": losses,
            "dataset_fingerprint": split["dataset_fingerprint"],
            "initial_logit_error": error,
        }
        atomic_json(staging / "unit_classifier.json", metadata)
        for suffix in (".json", ".onnx", ".onnx.data"):
            shutil.copy2(
                current / ("star_level_classifier" + suffix),
                staging / ("star_level_classifier" + suffix),
            )
        proposed = CPUClassifier(
            staging, "unit_classifier", set_number=metadata["set_number"]
        )
        candidate_logits = proposed.session.run(
            None, {proposed.session.get_inputs()[0].name: sample}
        )[0]
        with torch.no_grad():
            trained_logits = model(torch.from_numpy(sample)).numpy()
        if not np.allclose(candidate_logits, trained_logits, rtol=0.0001, atol=0.0001):
            raise ValueError("Candidate ONNX export failed CPU parity")
        shutil.copytree(staging, output)
    return metadata["training"]
