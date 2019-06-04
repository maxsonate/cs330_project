import json
import logging
import os

import numpy as np
import torch

from emmental.data import EmmentalDataLoader, EmmentalDataset
from task_config import SuperGLUE_LABEL_MAPPING, SuperGLUE_TASK_SPLIT_MAPPING
from tokenizer import get_tokenizer

logger = logging.getLogger(__name__)


def get_CB_dataloaders(
    data_dir,
    task_name="CB",
    splits=["train", "val", "test"],
    max_data_samples=None,
    max_sequence_length=128,
    tokenizer_name="bert-base-uncased",
    batch_size=16,
    slice_func_dict = {},
):
    """Load CB data and return dataloaders"""

    def parse_jsonl(jsonl_path):
        print(jsonl_path)
        rows = [json.loads(row) for row in open(jsonl_path, encoding="utf-8")]
        print(rows[0])
        # Truncate to max_data_samples
        if max_data_samples:
            rows = rows[:max_data_samples]

        uids = []
        sent1s = []
        sent2s = []
        labels = []

        bert_token_ids = []
        bert_token_masks = []
        bert_token_segments = []

        for sample in rows:
            index = sample["idx"]
            sent1 = sample["premise"]
            sent2 = sample["hypothesis"]
            label = sample["label"] if "label" in sample else "entailment"

            uids.append(index)
            sent1s.append(sent1)
            sent2s.append(sent2)
            labels.append(SuperGLUE_LABEL_MAPPING[task_name][label])

            # Tokenize sentences
            sent1_tokens = tokenizer.tokenize(sent1)
            sent2_tokens = tokenizer.tokenize(sent2)

            while True:
                total_length = len(sent1_tokens) + len(sent2_tokens)
                # Account for [CLS], [SEP], [SEP] with "- 3"
                if total_length <= max_sequence_length - 3:
                    break
                if len(sent1_tokens) > len(sent2_tokens):
                    sent1_tokens.pop()
                else:
                    sent2_tokens.pop()

            # Convert to BERT manner
            tokens = ["[CLS]"] + sent1_tokens + ["[SEP]"]
            token_segments = [0] * len(tokens)

            tokens += sent2_tokens + ["[SEP]"]
            token_segments += [1] * (len(sent2_tokens) + 1)

            token_ids = tokenizer.convert_tokens_to_ids(tokens)

            # Generate mask where 1 for real tokens and 0 for padding tokens
            token_masks = [1] * len(token_ids)

            # Append padding
            padding = [0] * (max_sequence_length - len(token_ids))

            token_ids += padding
            token_masks += padding
            token_segments += padding

            bert_token_ids.append(torch.LongTensor(token_ids))
            bert_token_masks.append(torch.LongTensor(token_masks))
            bert_token_segments.append(torch.LongTensor(token_segments))

        labels = torch.from_numpy(np.array(labels))

        return EmmentalDataset(
            name="SuperGLUE",
            X_dict={
                "uids": uids,
                "sent1": sent1s,
                "sent2": sent2s,
                "token_ids": bert_token_ids,
                "token_masks": bert_token_masks,
                "token_segments": bert_token_segments,
            },
            Y_dict={"labels": labels},
        )

    dataloaders = {}

    tokenizer = get_tokenizer(tokenizer_name)

    for split in splits:
        jsonl_path = os.path.join(
            data_dir, task_name, SuperGLUE_TASK_SPLIT_MAPPING[task_name][split]
        )
        dataset = parse_jsonl(jsonl_path)

        task_to_label_dict = {}        
    
        for slice_name, slice_func in slice_func_dict.items():
            ind, pred = slice_func(dataset)
            dataset.Y_dict.update({f"{task_name}_slice_ind_{slice_name}": ind, f"{task_name}_slice_pred_{slice_name}": pred})
            task_to_label_dict.update({f"{task_name}_slice_ind_{slice_name}": f"{task_name}_slice_ind_{slice_name}", f"{task_name}_slice_pred_{slice_name}": f"{task_name}_slice_pred_{slice_name}"})
        
        task_to_label_dict.update({task_name: "labels"})
        
        dataloaders[split] = EmmentalDataLoader(
            task_to_label_dict=task_to_label_dict,
            dataset=dataset,
            split=split,
            batch_size=batch_size,
            shuffle=split == "train",
        )
        logger.info(f"Loaded {split} for {task_name}.")

    return dataloaders