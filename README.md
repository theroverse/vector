# Vector — Nave de Limpeza Cirurgica do Theroverse

Desinstalacao avancada e rastreio de residuos **por evidencias**.
O Vector investiga o sistema, calcula um nivel de confianca
(`HIGH / MEDIUM / LOW`) para cada resto orfao e so sugere remocao
com confirmacao explicita, item a item.

> Filosofia: auditoria primeiro, delecao depois — e nunca no susto.

## Fontes varridas

- Pastas: `Program Files`, `Program Files (x86)`, `ProgramData`,
  `AppData (Local/Roaming)`, `Temp`
- Registro: hives `Uninstall`, chaves `Run`, `App Paths`
- Servicos (`sc query`) e tarefas agendadas (`schtasks`)

## Layout

```
vector/
├── vector-cli.py              # entry-point fino (igual athena.py/zeus.py)
├── pytest.ini                 # pythonpath=src, testpaths=tests
├── src/vector/                # pacote (settings, models, utils, ...)
│   └── scanners/              # filesystem, registry, services, tasks
└── tests/                     # pytest (21+ testes, sem tocar o sistema real)
```

> Nota: o entry-point chama-se `vector-cli.py` (e nao `vector.py`) de
> proposito — `vector.py` na raiz sombrearia o pacote `vector/` nos
> testes. O padrao Athena/Zeus (`athena.py`/`zeus.py`) so funciona la
> porque o pacote mora em `src/athena` com nome distinto do script.

## Uso

```powershell
python vector-cli.py                              # = --scan (auditoria)
python vector-cli.py --scan --target Notion       # investiga um programa
python vector-cli.py --scan --min-confidence MEDIUM -v
python vector-cli.py --scan --json relatorio.json # exporta p/ Orbit/automacao
python vector-cli.py --clean --target Notion      # limpeza interativa
```

## Seguranca

- `--scan` nunca apaga nada (exit code sempre 0).
- `--clean` exige digitacao literal `REMOVER <n>` + confirmacao `s/N`.
- Candidatos `LOW` nunca sao oferecidos no `--clean`.
- Allowlist protege `Microsoft`, `Windows`, drivers (`NVIDIA`, `Intel`...).
- Pastas com possivel dado sensivel (`save`, `backup`, `wallet`,
  `projeto`, `foto`) disparam alerta explicito.
- Registro, servicos e tarefas **nunca** sao removidos sozinhos:
  o relatorio mostra o comando manual para voce decidir.
- `PermissionError` e tratado com elegancia: o item entra na lista
  de `access_denied` com dica de rodar como admin.

## GUI (fase 1 — dados de exemplo)

A interface roda em uma janela WebView2 borderless (mesma arquitetura do
Genesis), com dados de exemplo ate a fase 2 ligar o motor Python real.

```powershell
gui\vector\dev.cmd          # preview no navegador (modo mock)
gui\VectorHost.ps1          # janela real (WebView2, pede admin)
.\build.ps1                 # compila dist\Vector.exe (arquivo unico)
```

Tela a tela: inicio → configuracao da varredura (alvo/confianca/verbose)
→ arvore de evidencias (badges HIGH/MEDIUM/LOW, pesos, alerta de dado
sensivel, comandos manuais para registro/servico/tarefa) → limpeza
interativa (digite `REMOVER <n>` + confirme; Enter sempre pula) → resumo
com log. O botao fechar confirma antes de sair.

## Build (padrao Genesis)

`build.ps1` gera o payload (zip → gzip → base64 de `gui/vector/` +
`gui/Vector.ico`), monta o script unico e compila com ps2exe.
Na fase 2, acrescentar `'src'` em `scripts/build-payload.ps1` embute o
motor Python. O exe extrai em `%LOCALAPPDATA%\Vector\app\<versao>` na
primeira execucao (sentinela: `gui\vector\app.js`) e guarda dados/cache
do WebView2 em `%LOCALAPPDATA%\Vector\WebView2`.

## Identidade

**Vector Magenta** — "Magenta Cirurgico & Rosa Plasma": primario
`#EC4899`, secundario `#DB2777`, acento `#F9A8D4`, campo escuro
`#14060f`. Cores dos irmaos (theroverse/src/data/ecosystem.ts):
Nexo ciano `#00D2FF`, Genesis violeta `#A855F7`, Athena esmeralda
`#10B981`, Zeus lima `#A3E635`, Thero laranja `#F97316` — magenta e o
matiz aberto do ecossistema.

## Testes

```powershell
python -m pytest tests/ -v      # motor (22 testes)
node --check gui/vector/app.js  # sintaxe da interface
```

