# Modly Progress

Affiche la progression **directement dans les nodes de Modly** : barre,
pourcentage, phase en cours, temps écoulé et estimation de la diffusion lorsque
les étapes réelles sont connues. Le panneau apparaît aussi dans l'onglet
**Generate**, au-dessus du bouton de génération.

Add-on communautaire indépendant pour [Modly, par Lightning Pixel](https://github.com/lightningpixel/modly).
Ce dépôt ne distribue ni Modly, ni ses modèles, ni vos données.

## Pourquoi un add-on d'interface ?

Le système d'extensions actuel ajoute des modèles et des traitements, mais ne
permet pas de remplacer l'interface des nodes. Ajouter un node de traitement
« observateur » ne suffirait pas : il s'exécuterait avant ou après le calcul.
Ce correctif utilise le store de progression déjà présent dans Modly et ajoute
un panneau aux nodes existants. **Ce n'est pas une extension à coller dans
« Install from GitHub ».** Aucun node supplémentaire n'est nécessaire.

## Installation (Windows)

Python 3.10+ requis, aucune dépendance Python supplémentaire.
Installation validée sur **Modly 0.4.3 sous Windows**, le 17 novembre 2026 ; les versions
dont la structure diffère sont refusées avant toute modification.

1. Télécharger ce dépôt ou le cloner.
2. Laisser finir les calculs, puis fermer Modly.
3. Dans le dossier du dépôt :

```powershell
python install.py --dry-run
python install.py
```

Relancer Modly, ouvrir un workflow puis lancer une génération. Le panneau
apparaît dans le node actif. L'installation crée une sauvegarde exacte et
affiche son emplacement. Les modèles, workflows et objets ne sont pas modifiés.

Pour Hunyuan3D Mini, après au moins une première génération ayant installé le
pipeline, activer aussi les **vraies étapes de diffusion** :

```powershell
python install.py --dry-run --hunyuan
python install.py --hunyuan
```

Cette option remplace la progression simulée par minuterie de l'adaptateur Mini
par le callback réel du pipeline Tencent. Elle conserve le contrôle d'annulation.
Le chargement, la suppression du fond, le décodage et l'export peuvent toujours
avoir une durée inconnue. Pendant ces phases, le panneau le dit explicitement.
Les autres générateurs restent inchangés : leur pourcentage est indiqué comme
« signalé par le modèle (peut être estimé) ».

## Ce que signifie le pourcentage

- `Diffusion 15/30` : 50 % **des étapes de diffusion**, pas du temps total.
- Temps restant de diffusion : estimation à partir des étapes déjà accomplies.
- Chargement/décodage : indicateur indéterminé, durée restante inconnue.
- Le chronomètre mesure le temps d'activité du node, y compris ses pauses.
- Le panneau disparaît à la fin du node. Il ne constitue pas un historique.

## Désinstallation

Fermer Modly et utiliser **le dossier exact indiqué lors de l'installation** :

```powershell
python install.py --restore "CHEMIN_DU_DOSSIER_DE_SAUVEGARDE"
```

Les empreintes sont vérifiées. Si Modly a été mis à jour depuis, l'outil refuse
d'écraser les fichiers de la nouvelle version. Une mise à jour de Modly peut
remplacer le correctif ; relancer d'abord `--dry-run` pour vérifier la compatibilité.

Si plusieurs versions de l'add-on ont été installées successivement, restaurer
leurs sauvegardes dans l'ordre inverse pour revenir à l'installation initiale.

Les chemins peuvent être précisés avec `--asar`, `--generator` et `--backups`.
Ne pas publier les sauvegardes : elles contiennent votre installation d'origine.

## Développement et tests

```powershell
python -m unittest discover -s tests -v
node --test tests/progress.test.cjs
```

L'installateur valide les points d'insertion, reconstruit l'ASAR en conservant
les autres fichiers et les références aux fichiers unpacked, actualise les
empreintes des fichiers changés et écrit chaque fichier de façon atomique.
En cas d'échec d'écriture, il restaure les changements déjà appliqués.

## Licence

MIT pour le code de cet add-on. Modly et Hunyuan3D conservent leurs licences et
attributions respectives. Le script modifie uniquement une installation locale.
