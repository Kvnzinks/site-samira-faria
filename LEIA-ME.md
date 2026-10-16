# Samira Faria — Site de agendamentos

Site completo e responsivo para agendamentos de sobrancelhas, micropigmentação e estética facial. Inclui área das clientes, administração, cadastro, login, agenda em tempo real e banco SQLite. Fotografias e identidade baseadas nas referências fornecidas.

## Como abrir no Windows

1. Extraia todo o arquivo `.zip` para uma pasta no computador.
2. Instale o **Python 3.10 ou mais recente** se ainda não tiver: https://www.python.org/downloads/ . Na instalação, marque **Add Python to PATH**.
3. Dê dois cliques em `start.bat`. O navegador abrirá em `http://127.0.0.1:8080`.
4. Mantenha a janela do servidor aberta enquanto usa o site. Para fechar o site local, feche a janela.

**Não precisa instalar pacotes extras.** Também funciona no Linux/macOS executando `python3 app.py` na pasta do projeto.

## Primeiro acesso administrativo

Na **primeira execução**, o terminal do servidor apresenta um e-mail de acesso administrativo e uma **senha inicial aleatória**, apenas uma vez. Anote-os antes de fechar o terminal. No site, clique em **Entrar** e acesse o painel. Em **Segurança**, mude a senha.

E-mail inicial: `admin@samira.local` (identificador local, não é uma caixa de e-mail real).

Se preferir definir os dados antes da primeira execução, use as variáveis de ambiente `ADMIN_EMAIL` e `ADMIN_PASSWORD` (mínimo de 10 caracteres). Em Windows PowerShell, por exemplo:

```powershell
$env:ADMIN_EMAIL="seu-email@example.com"
$env:ADMIN_PASSWORD="SuaSenhaLongaUnica!"
python app.py
```

**Atenção:** uma vez criado o banco, alterar essas variáveis não modifica o usuário já cadastrado. A senha pode ser alterada pelo painel administrativo.

## Recursos disponíveis

- Site de apresentação com foto, marca, tratamentos, informações e links de agendamento.
- Cadastro/login de clientes com senhas protegidas por PBKDF2.
- Seleção de tratamento, data e horários disponíveis a cada 30 minutos.
- A agenda respeita a duração real cadastrada, expediente, intervalo, datas bloqueadas e reservas prévias.
- Clientes conseguem consultar e cancelar seus agendamentos futuros.
- Painel administrativo com indicadores, tabela de reservas e alteração de status.
- Gerenciamento de tratamentos, preços opcionais, duração, descrição e publicação.
- Configuração dos dias/horários de atendimento e folgas.
- Edição de Instagram, WhatsApp, localização e textos.
- Persistência em `data/agenda.sqlite3`.

## Antes de usar com clientes reais

As durações, serviços, horários e observações iniciais são **dados de demonstração/editáveis**, pois as imagens não continham preços, duração e expediente detalhado. Confira tudo no painel antes de publicar. O site **não envia mensagens automaticamente**, mas pode abrir o WhatsApp com uma mensagem pronta após reservar. A cliente precisa tocar em **Enviar**. O site não recebe pagamentos e não está publicado na internet.

Para uso externo, escolha hospedagem com suporte a Python e arquivos persistentes, configure HTTPS e domínio, defina `COOKIE_SECURE=1`, proteja o acesso ao servidor, mantenha cópias de segurança do banco de dados e publique os avisos adequados de privacidade (LGPD). Não exponha o servidor de desenvolvimento sem endurecimento de segurança e infraestrutura de produção. Faça backup do arquivo `data/agenda.sqlite3` com o servidor parado ou usando o mecanismo de backup do SQLite.

### Organização

```text
app.py                 Servidor, autenticação, agenda e API
start.bat              Iniciador no Windows
start.sh               Iniciador Linux / macOS
static/index.html      Estrutura das páginas
static/style.css       Identidade visual e responsividade
static/app.js          Experiências de cliente e administração
static/assets/         Foto tratada e ícone de marca
data/                   Banco criado automaticamente na primeira execução
```

Desenvolvido para a identidade visual de Samira Faria — @sa.dbrows, São Paulo / Zona Norte.

## Redirecionamento após o agendamento (correção V2)

No **Painel Admin → Minha marca**, informe o **WhatsApp real da Samira com DDD** e selecione o comportamento após a reserva:

- **Abrir WhatsApp:** após a gravação do agendamento, abre o WhatsApp com procedimento, data, hora, nome e número da reserva. A cliente precisa enviar a mensagem. Se o número estiver vazio ou inválido, abre a área **Meus agendamentos** como alternativa.
- **Meus agendamentos:** abre automaticamente a área da cliente.
- **Somente confirmação:** permanece na tela de sucesso, com links para WhatsApp (quando cadastrado) e Minha conta.

Para atualizar instalações existentes, **feche o servidor**, copie `app.py`, `static/app.js` e `static/index.html` do pacote de correção para a pasta do site substituindo os anteriores e reinicie. **Não substitua a pasta `data/`**: ela contém suas clientes e reservas. O campo novo de configuração é criado automaticamente ao iniciar o servidor, sem apagar configurações já existentes.


Atualização V3: logo trocado para o novo monograma enviado, foto principal atualizada em alta qualidade e WhatsApp padrão configurado como 11 94922-2083, com redirecionamento após agendamento.
