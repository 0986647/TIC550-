
import socket
import sys
import re
from email.header import Header


def recevoir_reponse(reader):
    """Lit une réponse SMTP complète, y compris les réponses multilignes."""
    lignes = []

    while True:
        ligne = reader.readline()

        if not ligne:
            raise ConnectionError("Connexion fermée par le serveur SMTP.")

        texte = ligne.decode("utf-8", errors="replace").rstrip("\r\n")
        lignes.append(texte)

        
        if (
            len(texte) >= 4
            and texte[:3].isdigit()
            and texte[3] == " "
        ):
            break

        if len(texte) < 4 or not texte[:3].isdigit():
            raise RuntimeError(f"Réponse SMTP invalide : {texte!r}")

    reponse = "\n".join(lignes)
    print(f"S: {reponse}")
    return int(lignes[-1][:3]), reponse


def envoyer_commande(sock, reader, commande, codes_attendus):
    """Envoie une commande SMTP et vérifie son code de réponse."""
    print(f"C: {commande}")
    sock.sendall((commande + "\r\n").encode("ascii"))

    code, reponse = recevoir_reponse(reader)

    if code not in codes_attendus:
        raise RuntimeError(
            f"Commande refusée ({code}) : {reponse}"
        )

    return code, reponse


def appliquer_dot_stuffing(texte):
    """Normalise les fins de ligne et protège les lignes commençant par un point."""
    texte = texte.replace("\r\n", "\n").replace("\r", "\n")
    lignes = texte.split("\n")

    return "\r\n".join(
        "." + ligne if ligne.startswith(".") else ligne
        for ligne in lignes
    )


def valider_champ(nom, valeur):
    """Empêche l'injection de lignes dans les commandes ou les en-têtes."""
    if not isinstance(valeur, str) or not valeur.strip():
        raise ValueError(f"Champ vide ou invalide : {nom}")

    if "\r" in valeur or "\n" in valeur:
        raise ValueError(f"Retour à la ligne interdit dans : {nom}")


def envoyer_courriel_brut(
    host, port, expediteur, destinataire, sujet, corps
):
    """Exécute une session SMTP complète."""

    sock = None

    try:
        for nom, valeur in (
            ("host", host),
            ("expediteur", expediteur),
            ("destinataire", destinataire),
            ("sujet", sujet),
        ):
            valider_champ(nom, valeur)

        
        adresse_regex = r"^[^@\s<>]+@[^@\s<>]+$"

        for nom, adresse in (
            ("expediteur", expediteur),
            ("destinataire", destinataire),
        ):
            if not re.fullmatch(adresse_regex, adresse):
                raise ValueError(f"Adresse invalide ({nom}) : {adresse}")

        
        sock = socket.create_connection((host, port), timeout=5)
        sock.settimeout(10)

        
        reader = sock.makefile("rb")

        try:
            
            code, _ = recevoir_reponse(reader)
            if code != 220:
                raise RuntimeError(
                    f"Bannière SMTP inattendue : {code}"
                )

            
            envoyer_commande(
                sock, reader, "EHLO localhost", {250}
            )

            
            envoyer_commande(
                sock, reader,
                f"MAIL FROM:<{expediteur}>", {250}
            )

            
            envoyer_commande(
                sock, reader,
                f"RCPT TO:<{destinataire}>", {250, 251}
            )

            
            envoyer_commande(sock, reader, "DATA", {354})

            
            sujet_encode = Header(sujet, "utf-8").encode()

            entetes = (
                f"From: <{expediteur}>\r\n"
                f"To: <{destinataire}>\r\n"
                f"Subject: {sujet_encode}\r\n"
                "MIME-Version: 1.0\r\n"
                'Content-Type: text/plain; charset="utf-8"\r\n'
                "Content-Transfer-Encoding: 8bit\r\n"
                "\r\n"
            )

            corps_protege = appliquer_dot_stuffing(corps)

            
            message = entetes + corps_protege
            message = message.rstrip("\r\n") + "\r\n.\r\n"

            print("C: [contenu du message]")
            sock.sendall(message.encode("utf-8"))

            code, reponse = recevoir_reponse(reader)
            if code != 250:
                raise RuntimeError(
                    f"Message refusé après DATA : {reponse}"
                )

            print("Message accepté par le serveur SMTP.")

            
            envoyer_commande(sock, reader, "QUIT", {221})

        finally:
            reader.close()

    except (OSError, ConnectionError, RuntimeError, ValueError) as exc:
        print(
            f"Erreur lors de la session SMTP : {exc}",
            file=sys.stderr,
        )
        return False

    finally:
        if sock is not None:
            sock.close()

    return True


if __name__ == "__main__":
    print("--- DÉBUT DE LA SESSION SMTP BRUTE ---")

    corps_test = (
        "Bonjour,\n"
        "Ceci est un message brut envoyé via socket.\n"
        ".Une ligne commençant par un point."
    )

    succes = envoyer_courriel_brut(
        host="localhost",
        port=1025,
        expediteur="test@isteah.edu.ht",
        destinataire="etudiant@etudiant.test",
        sujet="Test Client Brut",
        corps=corps_test,
    )

    print("--- FIN DE LA SESSION ---")
    sys.exit(0 if succes else 1)
