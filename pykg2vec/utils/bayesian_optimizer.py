#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This module is for performing bayesian optimization on algorithms
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import importlib

from hyperopt import hp, fmin, tpe, Trials, STATUS_OK, space_eval
import pandas as pd


from pykg2vec.utils.kgcontroller import KnowledgeGraph
from pykg2vec.utils.trainer import Trainer
from pprint import pprint

model_path = "pykg2vec.core"
config_path = "pykg2vec.config.config"
hyper_param_path = "pykg2vec.config.hyperparams"

modelMap = {"complex": "Complex",
            "conve": "ConvE",
            "hole": "HoLE",
            "distmult": "DistMult",
            "kg2e": "KG2E",
            "ntn": "NTN",
            "proje_pointwise": "ProjE_pointwise",
            "rescal": "Rescal",
            "rotate": "RotatE",
            "slm": "SLM",
            "sme": "SME",
            "transd": "TransD",
            "transe": "TransE",
            "transg": "TransG",
            "transh": "TransH",
            "transm": "TransM",
            "transr": "TransR",
            "tucker": "TuckER"}


configMap = {"complex": "ComplexConfig",
             "conve": "ConvEConfig",
             "hole": "HoLEConfig",
             "distmult": "DistMultConfig",
             "kg2e": "KG2EConfig",
             "ntn": "NTNConfig",
             "proje_pointwise": "ProjE_pointwiseConfig",
             "rescal": "RescalConfig",
             "rotate": "RotatEConfig",
             "slm": "SLMConfig",
             "sme": "SMEConfig",
             "transd": "TransDConfig",
             "transe": "TransEConfig",
             "transg": "TransGConfig",
             "transh": "TransHConfig",
             "transm": "TransMConfig",
             "transr": "TransRConfig",
             "tucker": "TuckERConfig"}


hypMap = {"complex": "ComplexParams",
          "conve": "ConvEParams",
          "hole": "HoLEParams",
          "distmult": "DistMultParams",
          "kg2e": "KG2EParams",
          "ntn": "NTNParams",
          "proje_pointwise": "ProjE_pointwiseParams",
          "rescal": "RescalParams",
          "rotate": "RotatEParams",
          "slm": "SLMParams",
          "sme": "SMEParams",
          "transd": "TransDParams",
          "transe": "TransEParams",
          "transg": "TransGParams",
          "transh": "TransHParams",
          "transm": "TransMParams",
          "transr": "TransRParams",
          "tucker": "TuckERParams"}


class BaysOptimizer(object):
    """Bayesian optimizer class for tuning hyperparameter.

      This class implements the Bayesian Optimizer for tuning the 
      hyper-parameter.

      Args:
        args (object): The Argument Parser object providing arguments.
        name_dataset (str): The name of the dataset.
        sampling (str): sampling to be used for generating negative triples


      Examples:
        >>> from pykg2vec.config.hyperparams import KGETuneArgParser
        >>> from pykg2vec.utils.bayesian_optimizer import BaysOptimizer
        >>> model = Complex()
        >>> args = KGETuneArgParser().get_args(sys.argv[1:])
        >>> bays_opt = BaysOptimizer(args=args)
        >>> bays_opt.optimize()
    """

    def __init__(self, args=None):
        """store the information of database"""
        if args.model.lower() in ["tucker", "tucker_v2", "conve", "convkb", "proje_pointwise"]:
          raise Exception("Model %s has not been supported in tuning hyperparameters!" % args.model)

        model_name = args.model.lower()
        self.args = args
        self.knowledge_graph = KnowledgeGraph(dataset=args.dataset_name, custom_dataset_path=args.dataset_path)
        hyper_params = None
        try:
            self.model_obj = getattr(importlib.import_module(model_path + ".%s" % modelMap[model_name]),
                                     modelMap[model_name])
            self.config_obj = getattr(importlib.import_module(config_path), configMap[model_name])
            hyper_params = getattr(importlib.import_module(hyper_param_path), hypMap[model_name])()

        except ModuleNotFoundError:
            print("%s not implemented! Select from: %s" % \
                 (model_name, ' '.join(map(str, modelMap.values()))))
        
        from pykg2vec.config.config import KGEArgParser
        kge_args = KGEArgParser().get_args([])
        kge_args.dataset_name = args.dataset_name
        config = self.config_obj(kge_args)

        self.trainer = Trainer(model=self.model_obj(config), debug=self.args.debug, tuning=True)
        
        self.search_space = hyper_params.search_space
        self.max_evals = self.args.max_number_trials if not self.args.debug else 1
        
    def optimize(self):
        """Function that performs bayesian optimization"""
        trials = Trials()
        
        self.best_result = fmin(fn=self.get_loss, space=self.search_space, trials=trials,
                                algo=tpe.suggest, max_evals=self.max_evals)
        
        columns = list(self.search_space.keys())   
        results = pd.DataFrame(columns=['iteration'] + columns + ['loss'])
        
        for idx, trial in enumerate(trials.trials):
            row = []
            row.append(idx)
            translated_eval = space_eval(self.search_space, {k: v[0] for k, v in trial['misc']['vals'].items()})
            for k in columns:
                row.append(translated_eval[k])
            row.append(trial['result']['loss'])
            results.loc[idx] = row

        path = self.trainer.config.result / self.trainer.model.model_name 
        path.mkdir(parents=True, exist_ok=True)
        results.to_csv(str(path / "trials.csv"), index=False)
        
        print(results)
        print('Found Golden Setting:')
        pprint(space_eval(self.search_space, self.best_result))

    def return_best(self):
        """Function to return the best hyper-parameters"""
        return space_eval(self.search_space, self.best_result)

    def get_loss(self, params):
        """Function that defines and acquires the loss"""
        
        # copy the hyperparameters to trainer config and hyperparameter set. 
        for key, value in params.items():
          self.trainer.config.__dict__[key] = value
          self.trainer.config.hyperparameters[key] = value  
        
        # configure common setting for a tuning training. 
        self.trainer.config.disp_result = False
        self.trainer.config.disp_summary = False
        self.trainer.config.save_model = False
        self.trainer.config.test_num = 1000

        if self.args.debug:
          self.trainer.config.epochs = 1
          self.trainer.config.hyperparameters['epochs'] = 1
        
        # start the trial.
        self.trainer.build_model()
        self.trainer.summary_hyperparameter()
    
        loss = self.trainer.tune_model()

        return {'loss': loss, 'status': STATUS_OK}