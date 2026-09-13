"""Exécution réelle du moteur E-CMA sur le dossier d'Ahmed.

Lancer :  cd ~/mizan && source .venv/bin/activate && python packages/ecma/demo_ahmed.py

Sortie complète : l'avis de l'agent, l'état de l'espace de validation (vide),
les articles cités avec leur contre-épreuve BM25, et le projet de
procès-verbal dans les deux langues.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from datetime import date  # noqa: E402

from reglement import Litige, Partie, proposer_reglement, rediger_pv  # noqa: E402

AUJOURDHUI = date(2026, 9, 13)


def main() -> None:
    litige = Litige(
        montant_reclame=9520.0,
        nature="Travaux de menuiserie — fourniture et pose",
        demandeur=Partie(
            nom='Menuiserie Ahmed',
            role='demandeur',
            position="Les travaux ont été livrés et réceptionnés sans réserve "
                     "écrite. La facture reste impayée depuis quatre mois.",
        ),
        defendeur=Partie(
            nom='Société El Amen SARL',
            role='defendeur',
            position="Le client conteste la qualité : plusieurs ouvrants "
                     "ferment mal et les finitions ne sont pas conformes au "
                     "devis.",
        ),
        date_facture='2026-05-12',
        numero_facture='2026-041',
        lieu='Sfax',
    )

    dossier = proposer_reglement(litige, aujourdhui=AUJOURDHUI,
                                 controler_ancrage=True)

    print('=' * 78)
    print(f"DOSSIER {dossier.reference}")
    print('=' * 78)
    print(f"porte_effet_juridique : {dossier.porte_effet_juridique}")
    print(f"est_projet            : {dossier.est_projet}")
    print(f"validation.valide_par : {dossier.validation.valide_par!r}")
    print(f"validation.signe      : {dossier.validation.signe}")
    print(f"avis.contraignant     : {dossier.avis.contraignant}")
    print()

    v = dossier.avis.voie_recommandee
    print('--- VOIE RECOMMANDÉE ------------------------------------------------')
    print(f"{v['voie']['nom_fr']} ({v['voie']['nom_ar']})")
    print(f"  Rôle du tiers   : {v['voie']['role_du_tiers']}")
    print(f"  Effet de l'issue: {v['voie']['effet_de_lissue']}")
    for m in v['motifs']:
        print(f"  • {m}")
    print()
    print('  Les deux autres voies, et ce qui les distingue :')
    for cle in ('mediation', 'arbitrage'):
        w = v['voies_examinees'][cle]
        print(f"   - {w['nom_fr']} ({w['nom_ar']}) — {w['role_du_tiers']}")
        print(f"     fondée dans le corpus : {w['fondee_dans_corpus']}")
        if w['reserve']:
            print(f"     RÉSERVE : {w['reserve']}")
    print()

    p = dossier.avis.prescription
    print('--- PRESCRIPTION ----------------------------------------------------')
    print(f"  calculable={p['calculable']}  échéance={p.get('echeance')}  "
          f"jours restants={p.get('jours_restants')}  "
          f"prescrite={p.get('est_prescrite')}")
    print(f"  source : {p['source']['short_fr']} — {p['source']['citation_ar']}")
    print()

    print('--- TERMES PROPOSÉS -------------------------------------------------')
    for t in dossier.avis.termes:
        print(f"\n  [{t['cle']}] {t['intitule_fr']} — {t['intitule_ar']}")
        print(f"    principe_fonde={t['principe_fonde']}  "
              f"quantum_fonde={t['quantum_fonde']}")
        print(f"    {t['detail_fr']}")
        if t['valeur']:
            print(f"    valeur : {t['valeur']}")
        if t['reserve']:
            print(f"    RÉSERVE : {t['reserve']}")
        for s in t['sources']:
            print(f"    ↳ {s['short_fr']} | {s['citation_ar']} | {s['fiabilite']}")
        for c in t['controles']:
            print(f"      contre-épreuve BM25 : retrouvé={c['retrouve']} "
                  f"rang={c['rang_de_larticle']} score={c['meilleur_score']} "
                  f"gate_grounded={c['gate_grounded']}")
    print()

    print('--- CE QUE LE CORPUS NE FONDE PAS -----------------------------------')
    for x in dossier.avis.abstentions:
        print(f"  – {x}")
    print()

    pv = rediger_pv(dossier)
    print('=' * 78)
    print('PROJET DE PROCÈS-VERBAL — VERSION FRANÇAISE')
    print('=' * 78)
    print(pv['texte_fr'])
    print()
    print('=' * 78)
    print('مشروع محضر صلح — النسخة العربية')
    print('=' * 78)
    print(pv['texte_ar'])
    print()

    print('=' * 78)
    print("APRÈS VALIDATION PAR UN PROFESSIONNEL ACCRÉDITÉ")
    print('=' * 78)
    dossier.valider(
        nom='Me Leila Trabelsi', qualite='conciliateur',
        numero_accreditation='CONC-SFX-0417',
        observations="Abattement arrêté à 12 % au vu du constat contradictoire "
                     "du 2 septembre 2026. Échéancier ramené à 3 mensualités.",
        le='2026-09-14',
    )
    print(f"porte_effet_juridique : {dossier.porte_effet_juridique}")
    print(f"validation.signature  : {dossier.validation.signature}")
    pv2 = rediger_pv(dossier)
    print(f"mention de projet encore présente ? "
          f"{'PROJET — NON SIGNÉ' in pv2['texte_fr']}")


if __name__ == '__main__':
    main()
