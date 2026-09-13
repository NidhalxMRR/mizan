"""Les cinq rôles de Mizan et les privilèges attachés à chacun.

Ce fichier est la transposition serveur de `web/lib/auth.ts`. L'interface
décidait déjà quels boutons afficher ; elle ne décidait rien de plus. Tant que
la matrice ne vit qu'au navigateur, cacher un bouton n'empêche personne
d'appeler la route qui se trouve derrière. La même matrice doit donc exister
côté serveur, et c'est celle-ci qui fait autorité.

Les deux listes sont volontairement identiques, à la virgule près. Le test
`test_comptes.py::test_la_matrice_serveur_est_identique_a_celle_du_navigateur`
relit le fichier TypeScript et échoue si quelqu'un modifie l'un sans l'autre.
Un privilège qui divergerait entre les deux serait une faille silencieuse :
l'écran promettrait une action que le serveur refuse, ou pire, le serveur
autoriserait une action que l'écran croit avoir masquée.
"""
from __future__ import annotations


class RoleInconnu(ValueError):
    """Le rôle demandé ne fait pas partie des cinq rôles de la plateforme."""


# L'ordre est celui de `web/lib/auth.ts` : administration, puis les quatre
# acteurs du litige dans l'ordre où ils interviennent.
ROLES: tuple[str, ...] = (
    "platform_admin",   # exploitation de la plateforme
    "msme",             # la PME : dépose, consulte, accepte
    "accredited_pro",   # médiateur · conciliateur · arbitre agréé
    "court_clerk",      # greffier du tribunal de commerce
    "huissier",         # عدل منفذ — monopole légal de la signification
)


PERMISSIONS: dict[str, tuple[str, ...]] = {
    "platform_admin": (
        "manage_tenants",
        "manage_users",
        "view_all",
        "manage_corpus",
    ),
    "msme": (
        "upload_evidence",       # brief §4.1 — contrats, bons, factures
        "view_own_case",
        "request_notice",        # demande le projet d'acte ; ne le signifie pas
        "open_ecma",             # ouvre une conciliation / médiation
        "accept_settlement",     # accepte un projet de صلح (COC art. 1458)
        "choose_professional",
    ),
    "accredited_pro": (
        "view_assigned_case",
        "conduct_ecma",
        "draft_settlement",
        "sign_settlement",       # PV de conciliation — brief §6
        "request_missing_piece",
    ),
    "court_clerk": (
        "view_queue",            # module institutionnel obligatoire — brief §4
        "review_evidence",
        "approve_dossier",
        "schedule_mediation",
        "export_dossier",
    ),
    "huissier": (
        "view_notice_request",
        "issue_formal_notice",   # le seul à pouvoir signifier — CPCC art. 5 et 60
        "record_service",        # consigne la date de signification
    ),
}


# Libellés affichés. Les messages d'erreur de ce paquet seront lus par des
# juristes, pas par des développeurs : on nomme les acteurs comme le droit les
# nomme, jamais par leur identifiant technique.
LIBELLES: dict[str, str] = {
    "platform_admin": "Administrateur",
    "msme": "Entreprise",
    "accredited_pro": "Professionnel accrédité",
    "court_clerk": "Greffier",
    "huissier": "Huissier de justice",
}

LIBELLES_AR: dict[str, str] = {
    "platform_admin": "مدير المنصة",
    "msme": "المؤسسة",
    "accredited_pro": "الوسيط المعتمد",
    "court_clerk": "كاتب المحكمة",
    "huissier": "عدل منفذ",
}


# Libellés des privilèges. Un refus qui dirait « permission issue_formal_notice
# manquante » n'apprendrait rien à un greffier. Un refus qui dit « signifier un
# acte » lui apprend ce qu'il a essayé de faire, et pourquoi la loi le lui
# refuse.
LIBELLES_PERMISSIONS: dict[str, str] = {
    "manage_tenants": "administrer les organisations",
    "manage_users": "administrer les comptes",
    "view_all": "consulter l'ensemble de la plateforme",
    "manage_corpus": "administrer le corpus juridique",
    "upload_evidence": "déposer des pièces",
    "view_own_case": "consulter son propre dossier",
    "request_notice": "demander un projet de mise en demeure",
    "open_ecma": "ouvrir une conciliation ou une médiation",
    "accept_settlement": "accepter un projet de règlement amiable",
    "choose_professional": "choisir un professionnel accrédité",
    "view_assigned_case": "consulter un dossier qui lui est confié",
    "conduct_ecma": "conduire la conciliation ou la médiation",
    "draft_settlement": "rédiger un projet de règlement amiable",
    "sign_settlement": "signer le procès-verbal de conciliation",
    "request_missing_piece": "réclamer une pièce manquante",
    "view_queue": "consulter la file du greffe",
    "review_evidence": "contrôler les pièces déposées",
    "approve_dossier": "déclarer un dossier recevable",
    "schedule_mediation": "fixer une date de médiation",
    "export_dossier": "exporter un dossier",
    "view_notice_request": "consulter une demande de signification",
    "issue_formal_notice": "signifier une mise en demeure",
    "record_service": "consigner la date de signification",
}


def libelle_role(role: str) -> str:
    """Le nom lisible d'un rôle, ou l'identifiant brut si le rôle est inconnu."""
    return LIBELLES.get(role, role)


def libelle_permission(permission: str) -> str:
    """Le nom lisible d'un privilège, ou l'identifiant brut s'il est inconnu."""
    return LIBELLES_PERMISSIONS.get(permission, permission)


def verifier_role(role: str) -> str:
    """Renvoie le rôle s'il existe, et refuse bruyamment sinon.

    Ce refus est la première barrière de l'inscription. Sans lui, une faute de
    frappe dans le formulaire créerait un compte sans aucun privilège — un
    compte muet, dont personne ne comprendrait pourquoi il ne peut rien faire.
    Mieux vaut refuser la création que livrer un compte inerte.
    """
    if role not in PERMISSIONS:
        connus = ", ".join(f"« {libelle_role(r)} »" for r in ROLES)
        raise RoleInconnu(
            f"Le rôle « {role} » n'existe pas sur Mizan. "
            f"Les rôles possibles sont : {connus}."
        )
    return role


def permissions_du_role(role: str) -> tuple[str, ...]:
    """Les privilèges attachés au rôle, dans l'ordre de la matrice.

    C'est la fonction qui répond à la promesse faite à l'inscription : le rôle
    choisi apporte ses privilèges avec lui, personne n'a à les attribuer à la
    main ensuite. Un privilège ne s'ajoute donc pas compte par compte : il
    s'ajoute au rôle, ici, et tous les comptes de ce rôle l'obtiennent.
    """
    return PERMISSIONS[verifier_role(role)]


def peut(role: str, permission: str) -> bool:
    """Vrai si ce rôle porte ce privilège.

    Un rôle inconnu répond faux plutôt que de lever : cette fonction sert à
    décider d'un affichage autant qu'à décider d'un accès, et un affichage ne
    doit pas tomber en panne parce qu'une donnée est abîmée. Le refus par
    défaut est le comportement sûr.
    """
    return permission in PERMISSIONS.get(role, ())
