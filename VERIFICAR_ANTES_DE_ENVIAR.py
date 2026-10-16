from pathlib import Path
import sys

root = Path(__file__).resolve().parent
arquivos = [
    "app.py", "Dockerfile", "static/index.html",
    "static/app.js", "static/style.css",
    "static/assets/samira-monograma.webp", "static/assets/samira-retrato.webp"
]
faltando = [nome for nome in arquivos if not (root / nome).is_file()]
print("SAMIRA FARIA — VERIFICAÇÃO DE PUBLICAÇÃO")
for nome in arquivos:
    print(("FALTA" if nome in faltando else "OK") + "  " + nome)
if faltando:
    print("\nNão publique antes de corrigir os arquivos ausentes.")
    sys.exit(1)
print("\nPronto para enviar ao GitHub.")
print("O GitHub deve mostrar app.py e Dockerfile na raiz, e index.html dentro de static/.")
