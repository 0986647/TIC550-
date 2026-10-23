import os
import re
import csv
import sys
import time
import uuid
import ssl
import smtplib
import logging
import argparse
import mimetypes

from pathlib import Path
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid, formatdate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("send_mail")

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$"
)

CHAMPS_REQUIS = ["nom", "email", "filière", "salle", "horaire"]


def valider_contact(row, line_num):
    """Valide les données d'une ligne du CSV."""

    for champ in CHAMPS_REQUIS:
        valeur = row.get(champ)

        if not isinstance(valeur, str) or not valeur.strip():
            logger.warning(
                "Ligne %s ignorée : champ manquant ou vide '%s'.",
                line_num,
                champ,
            )
            return False

    email = row["email"].strip()

    if not EMAIL_REGEX.fullmatch(email):
        logger.warning(
            "Ligne %s ignorée : adresse courriel invalide '%s'.",
            line_num,
            email,
        )
        return False

    return True


def generer_message(row, args, text_tmpl, html_tmpl):
    """Construit un courriel texte/HTML avec pièce jointe facultative."""

    msg = EmailMessage()

    msg["Subject"] = args.subject
    msg["From"] = os.getenv(
        "SMTP_FROM", "secretariat@isteah.edu.ht"
    )
    msg["To"] = row["email"].strip()
    msg["Reply-To"] = os.getenv(
        "SMTP_REPLY_TO", "no-reply@isteah.edu.ht"
    )
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    corps_texte = text_tmpl.format_map(row)
    corps_html = html_tmpl.format_map(row)

    msg.set_content(corps_texte)
    msg.add_alternative(corps_html, subtype="html")

    if args.attach:
        chemin = Path(args.attach)

        if not chemin.is_file():
            raise FileNotFoundError(
                f"Pièce jointe introuvable : {chemin}"
            )

        contenu = chemin.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(chemin))

        if mime_type:
            maintype, subtype = mime_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"

        msg.add_attachment(
            contenu,
            maintype=maintype,
            subtype=subtype,
            filename=chemin.name,
        )

    return msg


def logger_rapport(writer, email, statut, code="", msg=""):
    """Ajoute une ligne au rapport CSV."""

    writer.writerow([
        email,
        statut,
        code,
        msg,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ])



def envoyer_courriel_avec_retry(server, msg, dest_email):
    """Effectue une relance pour certaines erreurs SMTP temporaires."""

    for tentative in range(2):
        try:
            server.send_message(msg)
            return "SUCCÈS", "", ""

        except smtplib.SMTPRecipientsRefused as exc:
            logger.error(
                "Destinataire refusé pour %s : %s",
                dest_email,
                exc,
            )
            return "ÉCHEC", "RECIPIENT_REFUSED", str(exc)

        except smtplib.SMTPResponseException as exc:
            code = exc.smtp_code
            erreur = (
                exc.smtp_error.decode("utf-8", errors="replace")
                if isinstance(exc.smtp_error, bytes)
                else str(exc.smtp_error)
            )

            if 400 <= code < 500 and tentative == 0:
                logger.warning(
                    "Erreur temporaire SMTP %s pour %s. "
                    "Nouvelle tentative dans 2 secondes.",
                    code,
                    dest_email,
                )
                time.sleep(2)
                continue

            logger.error(
                "Échec SMTP %s pour %s : %s",
                code,
                dest_email,
                erreur,
            )
            return "ÉCHEC", str(code), erreur

        except (smtplib.SMTPServerDisconnected, OSError) as exc:
            logger.error(
                "Connexion SMTP perdue pour %s : %s",
                dest_email,
                exc,
            )
            return "ÉCHEC", "DISCONNECTED", str(exc)

        except Exception as exc:
            logger.exception(
                "Erreur inattendue lors de l'envoi à %s",
                dest_email,
            )
            return "ÉCHEC", "UNKNOWN", str(exc)

    return "ÉCHEC", "UNKNOWN", "Nombre maximal de tentatives atteint"


def initialiser_connexion(args):
    """Établit une connexion SMTP selon la sécurité configurée."""

    host = os.getenv("SMTP_HOST", args.host)
    port = int(os.getenv("SMTP_PORT", str(args.port)))
    user = os.getenv("SMTP_USER", args.user)
    password = os.getenv("SMTP_PASSWORD", args.password)
    security = os.getenv("SMTP_SECURITY", args.security)

    if security == "ssl":
        server = smtplib.SMTP_SSL(
            host,
            port,
            context=ssl.create_default_context(),
            timeout=20,
        )
    else:
        server = smtplib.SMTP(host, port, timeout=20)

        if security == "starttls":
            server.starttls(context=ssl.create_default_context())

    try:
        if user:
            if not password:
                raise ValueError(
                    "Un mot de passe SMTP est requis si SMTP_USER est défini."
                )
            server.login(user, password)

        return server

    except Exception:
        try:
            server.quit()
        except Exception:
            pass
        raise



def main():
    parser = argparse.ArgumentParser(
        description="Outil de publipostage SMTP."
    )

    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1025)
    parser.add_argument(
        "--security",
        choices=["none", "starttls", "ssl"],
        default="none",
    )
    parser.add_argument("--user", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--attach")
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.delay < 0:
        parser.error("--delay doit être positif ou nul.")

    if args.port < 1 or args.port > 65535:
        parser.error("--port doit être compris entre 1 et 65535.")

    # Chargement des modèles.
    try:
        with open(
            "templates/convocation.txt", encoding="utf-8"
        ) as fichier:
            text_tmpl = fichier.read()

        with open(
            "templates/convocation.html", encoding="utf-8"
        ) as fichier:
            html_tmpl = fichier.read()

    except OSError as exc:
        logger.critical("Erreur de chargement des modèles : %s", exc)
        return 1

    server = None
    rapport_path = Path("rapport_envoi.csv")

    try:
        with open(
            args.csv, mode="r", encoding="utf-8-sig", newline=""
        ) as csv_file, open(
            rapport_path, mode="w", encoding="utf-8", newline=""
        ) as rapport_file:

            reader = csv.DictReader(csv_file)

            if not reader.fieldnames:
                logger.critical("Le fichier CSV est vide ou sans en-têtes.")
                return 1

            
            reader.fieldnames = [
                nom.strip() if nom else "" for nom in reader.fieldnames
            ]

            manquants = set(CHAMPS_REQUIS) - set(reader.fieldnames)

            if manquants:
                logger.critical(
                    "Colonnes CSV manquantes : %s",
                    ", ".join(sorted(manquants)),
                )
                return 1

            writer = csv.writer(rapport_file)
            writer.writerow([
                "adresse",
                "statut",
                "code_smtp",
                "message_erreur",
                "horodatage",
            ])

            
            if not args.dry_run:
                try:
                    server = initialiser_connexion(args)
                except Exception as exc:
                    logger.critical(
                        "Connexion SMTP impossible : %s", exc
                    )
                    return 1

            for numero, row in enumerate(reader, start=2):
                
                row = {
                    cle: valeur.strip() if isinstance(valeur, str) else ""
                    for cle, valeur in row.items()
                    if cle is not None
                }

                if not valider_contact(row, numero):
                    logger_rapport(
                        writer,
                        row.get("email", "Inconnu"),
                        "IGNORÉ",
                        "",
                        "Ligne invalide",
                    )
                    continue

                dest = row["email"]

                try:
                    msg = generer_message(
                        row, args, text_tmpl, html_tmpl
                    )
                except Exception as exc:
                    logger.exception(
                        "Erreur de génération à la ligne %s", numero
                    )
                    logger_rapport(
                        writer, dest, "ÉCHEC", "",
                        f"Erreur génération : {exc}",
                    )
                    continue

                if args.dry_run:
                    
                    nom_sûr = re.sub(
                        r"[^A-Za-z0-9_.-]", "_", dest
                    )
                    filename = (
                        f"convocation_{nom_sûr}_{uuid.uuid4().hex[:6]}.eml"
                    )

                    try:
                        with open(filename, "wb") as eml_file:
                            eml_file.write(msg.as_bytes())

                        logger.info(
                            "[DRY-RUN] Courriel sauvegardé : %s",
                            filename,
                        )
                        logger_rapport(
                            writer, dest, "DRY-RUN", "", ""
                        )

                    except OSError as exc:
                        logger.error(
                            "Impossible d'enregistrer le fichier : %s",
                            exc,
                        )
                        logger_rapport(
                            writer, dest, "ÉCHEC", "",
                            f"Écriture .eml : {exc}",
                        )

                else:
                    statut, code, erreur = envoyer_courriel_avec_retry(
                        server, msg, dest
                    )

                    logger_rapport(
                        writer, dest, statut, code, erreur
                    )

                    if statut == "SUCCÈS":
                        logger.info(
                            "Courriel envoyé à %s", dest
                        )

                    if code == "DISCONNECTED":
                        logger.critical(
                            "Connexion SMTP perdue. "
                            "Arrêt du traitement."
                        )
                        break

                    if args.delay > 0:
                        time.sleep(args.delay)

                
                rapport_file.flush()

    except (OSError, csv.Error) as exc:
        logger.critical("Erreur de traitement des fichiers : %s", exc)
        return 1

    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                logger.warning(
                    "La fermeture de la connexion SMTP a échoué."
                )

        logger.info(
            "Fin du traitement. Rapport : %s", rapport_path
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
                    
