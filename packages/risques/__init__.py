"""Analyse des risques juridiques d'une facture tunisienne, adossée au corpus.

Ce paquet ne produit un risque que s'il peut le rattacher à un article
réellement présent dans le corpus indexé. Quand le corpus est muet, il
s'abstient et le dit : voir `facture.analyser`.
"""
from .facture import Abstention, RapportRisques, Risque, analyser

__all__ = ['analyser', 'Risque', 'Abstention', 'RapportRisques']
