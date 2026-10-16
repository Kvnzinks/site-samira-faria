#!/data/data/com.termux/files/usr/bin/bash
# Opcional: executa o servidor direto no Android com Termux.
# Antes: pkg update && pkg install python
cd "$(dirname "$0")" || exit 1
export HOST=127.0.0.1
export PORT=8080
printf '\nSamira Faria: abra http://127.0.0.1:8080 no navegador Android.\nMantenha o Termux aberto para a agenda continuar ativa.\n'
python app.py
