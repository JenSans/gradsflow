from typing import List, Optional, Union

import optuna
import pytorch_lightning as pl
import torch
from flash.core.data.data_module import DataModule
from flash.image.classification import ImageClassifier
from optuna.integration import PyTorchLightningPruningCallback

from gradsflow.automodel.automodel import AutoModel


# noinspection PyTypeChecker
class AutoImageClassifier(AutoModel):
    DEFAULT_BACKBONES = ["ssl_resnet18", "ssl_resnet50"]

    def __init__(
        self,
        datamodule: DataModule,
        max_epochs: int = 10,
        optimization_metric: Optional[str] = None,
        suggested_backbones: Union[List, str, None] = None,
        n_trials: int = 100,
    ):
        super().__init__(datamodule, max_epochs, optimization_metric, n_trials)

        if not suggested_backbones:
            self.suggested_backbones = self.DEFAULT_BACKBONES
        elif isinstance(suggested_backbones, str):
            self.suggested_backbones = [suggested_backbones]
        elif isinstance(suggested_backbones, (list, tuple)):
            self.suggested_backbones = suggested_backbones
        else:
            raise UserWarning(f"Invalid suggested_backbone type!")

        self.datamodule = datamodule
        self.num_classes = datamodule.num_classes

    def forward(self, x):
        if not self.model:
            raise UserWarning("model not initialized yet!")
        return self.model(x)

    # noinspection PyTypeChecker
    def build_model(self, trial: optuna.Trial):
        optimizer = self.OPTIMIZER_INDEX

        trial_backbone = trial.suggest_categorical("backbone", self.suggested_backbones)
        trial_lr = trial.suggest_float("lr", 1e-5, 1e-1, log=True)
        trial_optimizer = trial.suggest_categorical(
            "optimizer", [optimizer["adam"], optimizer["sgd"]]
        )

        model = ImageClassifier(
            self.num_classes,
            backbone=trial_backbone,
            optimizer=trial_optimizer,
            learning_rate=trial_lr,
        )

        return model

    def objective(
        self,
        trial: optuna.Trial,
    ):
        trainer = pl.Trainer(
            logger=True,
            gpus=1 if torch.cuda.is_available() else None,
            max_epochs=self.max_epochs,
            callbacks=PyTorchLightningPruningCallback(
                trial, monitor=self.optimization_metric
            ),
        )
        model = self.build_model(trial)
        hparams = dict(model=model.hparams)
        trainer.logger.log_hyperparams(hparams)
        trainer.fit(model, datamodule=self.datamodule)

        return trainer.callback_metrics[self.optimization_metric].item()

    def fit(self):
        self.study.optimize(self.objective, n_trials=self.n_trials)
