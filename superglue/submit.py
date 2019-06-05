from collections import defaultdict
import logging
import os

import click
import jsonlines

from dataloaders import get_dataloaders
import emmental
from emmental.model import EmmentalModel
from models.cb import build_model as build_model_cb
from models.copa import build_model as build_model_copa
from models.multirc import build_model as build_model_multirc
from models.rte import build_model as build_model_rte
from models.wic import build_model as build_model_wic
from models.wsc import build_model as build_model_wsc
from task_config import SuperGLUE_LABEL_INVERSE, SuperGLUE_TASK_SPLIT_MAPPING

build_model = {
    "CB": build_model_cb,
    "COPA": build_model_copa,
    "MultiRC": build_model_multirc,
    "RTE": build_model_rte,
    "WiC": build_model_wic,
    "WSC": build_model_wsc,
}


CB_MODEL = "/path/to/model"
COPA_MODEL = "/path/to/model"
MultiRC_MODEL = "/path/to/model"
RTE_MODEL = "/path/to/model"
WiC_MODEL = "/path/to/model"
WSC_MODEL = "/path/to/model"

TASKS = ["CB", "COPA", "MultiRC", "RTE", "WiC", "WSC"]
BERT_MODEL_NAME = "bert-large-cased"


def format_multirc_preds(preds, dataloader):
    # Make prediction map
    paragraphs = paragraphs = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for idx, pred in enumerate(preds):
        pid = dataloader.dataset.X_dict["pids"][idx]
        qid = dataloader.dataset.X_dict["qids"][idx]
        aid = dataloader.dataset.X_dict["aids"][idx]
        paragraphs[pid][qid][aid] = pred
    # Moves indices from keys to sibling fields
    preds_formatted = []
    for pid, questions in paragraphs.items():
        p_dict = {"idx": pid, "paragraph": {"questions": []}}
        for qid, question in questions.items():
            q_dict = {"idx": qid, "answers": []}
            for aid, y in question.items():
                label = str(SuperGLUE_LABEL_INVERSE["MultiRC"][y]).lower()
                answer = {"idx": aid, "label": str(label)}
                q_dict["answers"].append(answer)
            p_dict["paragraph"]["questions"].append(q_dict)
        preds_formatted.append(p_dict)
    return preds_formatted


@click.command()
@click.option('--CB', default=CB_MODEL, help="Path to CB model")
@click.option('--COPA', default=COPA_MODEL, help="Path to COPA model")
@click.option('--MultiRC', default=MultiRC_MODEL, help="Path to MultiRC model")
@click.option('--RTE', default=RTE_MODEL, help="Path to RTE model")
@click.option('--WiC', default=WiC_MODEL, help="Path to WiC model")
@click.option('--WSC', default=WSC_MODEL, help="Path to WSC model")
@click.option('--split', default="test", type=click.Choice(["train", "val", "test"]))
@click.option('--data-dir', default=os.environ["SUPERGLUEDATA"])
@click.argument('name')
def make_submission(name, split, data_dir, cb, copa, multirc, rte, wic, wsc):
    submit_dir = f"submissions/{name}/"
    if not os.path.exists(os.path.dirname(submit_dir)):
        os.makedirs(os.path.dirname(submit_dir))
    
    for task_name, path in zip(TASKS, [cb, copa, multirc, rte, wic, wsc]):
        # TEMP
        # if task_name != "MultiRC":
        #     continue
        # TEMP
        task = build_model[task_name](BERT_MODEL_NAME)
        model = EmmentalModel(name=f"SuperGLUE_{task_name}", tasks=[task])
        try:
            model.load(path)
        except UnboundLocalError:
            msg = ("Failed to load state dict; confirm that your model was saved with "
                   "a command such as 'torch.save(model.state_dict(), PATH)'")
            logging.error(msg)
            raise
        dataloaders = get_dataloaders(
            data_dir,
            task_name=task_name,
            splits=["val", "test"], # TODO: replace with ['split'] and update below
            max_data_samples=None,
            # max_sequence_length=128,
            tokenizer_name=BERT_MODEL_NAME,
            batch_size=16,
            uid="uids",
        )
        # TEMP: Sanity check val performance
        logging.info(model.score(dataloaders[0]))
        # TEMP
        
        preds = model.predict(dataloaders[-1], return_preds=True)["preds"][task_name]
        if task_name == "MultiRC":
            preds_formatted = format_multirc_preds(preds, dataloaders[-1])
        else:
            preds_formatted = []
            for idx, y in enumerate(preds):
                label = str(SuperGLUE_LABEL_INVERSE[task_name][y]).lower()
                preds_formatted.append({"idx": idx, "label": label})

        filename = f'{task_name}.jsonl'
        filepath = os.path.join(submit_dir, filename)
        logging.info(f"Writing predictions to {filepath}")
        with jsonlines.open(filepath, mode='w') as writer:
            writer.write_all(preds_formatted)

    os.chdir(submit_dir)
    os.system("zip -r submission.zip *.jsonl")
    os.chdir("..")


if __name__ == '__main__':
    emmental.init()
    make_submission()