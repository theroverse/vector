# Vector — Limpeza em lote, linguagem humana e quarentena compactada

Data: 2026-09-21 · Branch: `feat/phase2-engine-bridge` · Status: aprovado pelo autor

## Problema

O fluxo de limpeza herdado do terminal (`--clean`: um item por vez, digitar
`REMOVER N` + confirmar) é custoso demais na GUI — num caso real foram 47
candidatos. E a informação apresentada (score cru, "+40 nome ausente nos
programas instalados") não dá a um usuário básico segurança para decidir se
pode ou não apagar uma pasta.

## Decisões (aprovadas em brainstorming)

1. **Agrupamento por nível de risco** (não por programa).
2. **Quarentena própria** com manifesto (não Lixeira, não hard delete).
3. **Restauração pela GUI** (telas Quarentena/Restauração), não só CLI —
   com diálogo de seleção em dois caminhos: último backup automático ou
   arquivo `.vec` informado pelo usuário (drag & drop / seletor nativo).
4. **Arquitetura A**: GUI orquestra o lote item a item; agrupamento é
   apresentação (JS); quarentena/zip/manifest/restore moram no Python.
5. **Quarentena guarda só a última execução**, compactada em arquivo único
   com extensão própria **`.vec`** (mesma lógica da Athena com `.atn.md`:
   dedicada pra não colidir), **portável** (manifesto dentro do zip) e
   **associada no Windows** — duplo-clique num `.vec` abre o Vector direto
   na tela de restauração.

## Fluxo novo (GUI)

`welcome → scan → review → plan → executing → done` + duas telas utilitárias
acessíveis a qualquer momento pela barra lateral: `quarantine` (backup
ativo) e o fluxo `restore` (abrir qualquer `.vec`).

Barra lateral ganha o item fixo **"Restaurar backup"** → modal na própria
WebView com **dois caminhos**:

1. **"Último backup automático"** (botão primário) — abre direto a tela de
   Restauração do `.vec` ativo da quarentena; mostra data/tamanho no
   próprio botão; desabilitado com explicação quando não há backup.
2. **"Outro arquivo…"** — só então aparece o formulário: zona de drag &
   drop + botão "Selecionar arquivo…" (OpenFileDialog nativo via host).
   Drop de arquivo no WebView2 expõe `File.path` (caminho local real); se
   algum runtime não expuser, o formulário orienta usar o botão.

O caminho escolhido vai ao engine (`backup-inspect`) e leva à **tela de
Restauração**.

### Revisão (review)

Lista dos candidatos do último scan, em 4 seções por risco, cada uma com
checkbox de grupo:

| Seção | Título para leigo | Seleção |
|---|---|---|
| HIGH não-sensível | "Quase certamente sobra de programa desinstalado" | pré-marcada |
| MEDIUM não-sensível | "Provável sobra — vale conferir" | livre (grupo marcável) |
| SENSITIVE | "Pasta com dados seus (configurações, conversas)" | nunca entra em "marcar todos"; marcável item a item |
| kind ≠ folder (REG/SVC/TASK) | "O Vector não apaga — veja o passo a passo" | não selecionável; mostra comando manual |

Cada candidato mostra:
- **nome legível** em destaque + caminho completo miúdo abaixo;
- **frase-motivo** em linguagem humana (campo `summaryPlain`, gerada no
  motor — ver abaixo), com tamanho e idade formatados;
- evidências técnicas (score, pesos, fontes) escondidas em
  "detalhes técnicos" expansível (`<details>`).

Rodapé fixo: "N selecionados · ~X GB" + botão "Revisar plano →". Sem
seleção, botão desabilitado.

### Plano (plan) — confirmação única

Resumo do que será movido: contagem por grupo selecionado, tamanho total
estimado, destino (quarentena). **Um único botão de confirmação**
"Mover N itens para quarentena". Confirmação digitada do terminal não é
replicada na GUI; a segurança vem do guard do motor + quarentena.

### Execução (executing) — estilo Genesis

Loop orquestrado pelo JS: para cada caminho selecionado, envia
`remove-folder {path}` ao host → engine (guard revalida contra o último
ScanReport; move para staging da quarentena). Feed item a item com
✓/✗ e motivo; falha em um item não interrompe o lote. Ao fim, JS envia
`quarantine-seal` (zipa o staging + escreve manifesto; descartando a
quarentena anterior) e segue para o relatório.

### Relatório (done)

Removidos / falharam / pulados, com o destino (quarentena) e dois botões:
**"Abrir quarentena"** e **"Salvar cópia do backup…"** (SaveFileDialog via
host; copia o `.vec` ativo para onde o usuário quiser — ex.: um pendrive —
sem tirar nada da quarentena).

### Tela Quarentena (backup ativo)

Mostra o `.vec` da última execução: data, tamanho do arquivo, itens
agrupados pelas mesmas seções de risco da Revisão. Botões:
**"Restaurar selecionados"** (loop item a item igual à Execução) e
**"Esvaziar"** (apaga o `.vec` — único ponto de apagamento definitivo da
quarentena). Sem backup: estado vazio explicativo. Restaurar **todos** os
itens do backup ativo remove o `.vec` ao final (quarentena esvaziada por
definição — guarda só a última execução).

### Tela Restauração (qualquer `.vec`, incluindo cópia exportada)

Mesma apresentação da Revisão (seções por risco, frase-motivo, checkbox de
grupo/item, seleção padrão idêntica) — os metadados de decisão (`kind`,
`confidence`, `sensitive`, `label`, `summaryPlain`, `original`, tamanho)
são lidos do manifesto **dentro** do arquivo, sem depender de scan nem de
máquina específica. Rodapé: "N itens selecionados · botão Restaurar
caminho". Execução em loop por item com feed ✓/✗.

**Semântica distinta (crítico):**
- backup **ativo** (quarentena): restaurar *move* de volta e remove a
  entrada do arquivo;
- `.vec` **externo** (copia exportada): restaurar *copia* de volta — o
  backup permanece intacto (é um backup, não uma lixeira).

## Motor (Python)

### `summaryPlain` no payload

Novo campo por candidato em `to_report_payload` e no `OrphanCandidate`:
uma frase em pt-BR derivada das evidências dominantes (ex.: "não está na
lista de programas instalados do Windows, mas ainda há pastas dele no
sistema"). Mapa fixo evidência→frase na mesma fonte dos textos de scoring;
evidências técnicas continuam em `evidences` (contrato `--json` do CLI
ganha o campo novo sem remover nada — aditivo, retrocompatível).

### `quarantine.py` (novo módulo)

- **Formato `.vec`**: zip (ZIP_DEFLATED) auto-contido — `manifest.json` na
  raiz do zip + itens sob `<id>/<caminho relativo>`. Manifesto por entrada:
  `{id, original, archived, sizeBytes, ts, kind, confidence, sensitive,
  label, summaryPlain}` + `sealed_ts` global. Tudo que a tela de
  Restauração precisa vive dentro do arquivo.
- local do backup ativo: `%LOCALAPPDATA%\Vector\quarantine\last.vec`;
  durante a execução os itens movidos ficam em `staging\` ao lado.
- `stage(candidate)` — move a pasta inteira para o staging (shutil.move);
  PermissionError vira falha reportada, nunca traceback.
- `seal()` — compacta staging no `last.vec`, **substitui** o backup
  anterior (retenção = só a última execução). Idempotente; staging órfão
  (queda no meio) é selado pelo primeiro acesso (`inspect`).
- `inspect(path)` / `restore_one(path, id, *, remove_entry)` /
  `restore_done(path)` / `purge()` / `export(dest)` — usados pelos comandos
  do bridge. `restore_one` com destino já existente → pula com motivo.
  `remove_entry=True` só para o backup ativo (move + enxuga o arquivo);
  para `.vec` externo é cópia e o arquivo não muda.
- Sem dependências novas (zipfile/pathlib/shutil da stdlib).

### Bridge — comandos novos

`remove` passa a mover para o staging da quarentena (assinatura/resposta
iguais, com `quarantined: true` + `sizeBytes`); novos: `quarantine-seal`,
`quarantine-inspect`, `quarantine-restore {id}` (por item, loop da GUI;
move de volta e enxuga o last.vec), `quarantine-purge`,
`quarantine-export {dest}`, `backup-inspect {path}` e
`backup-restore {path, id}` (copia de volta; backup intacto). O guard atual
(HIGH/MEDIUM only, só pasta, não-allowlisted, revalidação contra o report
em memória) vale para todo `remove` do lote, inalterado. CLI `--clean`
interativo do terminal mantém hard delete (comportamento auditado à parte;
a GUI é o produto com quarentena).

## Registro da extensão `.vec` no Windows

No boot do **exe empacotado** (nunca em modo dev/script), o VectorHost.ps1
garante a associação em **HKCU** (não exige admin; idempotente, barato):

```
HKCU\Software\Classes\.vec            = "Vector.Backup"
HKCU\Software\Classes\Vector.Backup\shell\open\command
    = "<caminho absoluto do Vector.exe>" --open "%1"
```

Duplo-clique num `.vec` → exe abre com `--open <caminho>` no `$args` →
após o WebView2 conectar, o host envia `open-backup {path}` → JS cai direto
na **tela de Restauração** daquele arquivo. Sem scan, sem admin necessário
para restaurar (a menos que o destino exija).

## Host (VectorHost.ps1)

Repasses novos (`quarantine-*`, `backup-*`, `open-backup` → `Invoke-Engine`
→ JS), sem regra nenhuma aqui. Dois diálogos nativos: OpenFileDialog
(selecionar `.vec`) e SaveFileDialog (exportar backup). Modelo síncrono 1:1
inalterado. Registro HKCU da extensão no boot (acima).

## Fora de escopo (YAGNI)

Retenção de mais de uma execução · criptografia do `.vec` · tela de
configurações · abrir `.vec` por linha de comando do Python (só pelo exe,
que é quem tem a associação registrada).

## Testes

- `test_quarantine.py`: stage/seal/inspect/restore_one (ativo move+
enxuga; externo copia e preserva)/purge/export com tmp_path (inclui:
  restore com destino já existente pula; seal substitui execução anterior;
  staging órfão é selado por inspect(); `.vec` é auto-contido — abre e
  restaura sem manifestos externos).
- `test_bridge.py`: novos comandos + `remove` quarentenando (remove_fn
  injetado) + `summaryPlain` presente no payload de scan.
- GUI: mock.js ganha candidatos com `summaryPlain` e a mesma estrutura de
  seções; fluxo completo revisável no preview do browser antes do rebuild
  do exe.
