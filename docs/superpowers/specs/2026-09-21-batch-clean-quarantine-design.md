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
3. **Restauração pela GUI** (tela Quarentena), não só CLI.
4. **Arquitetura A**: GUI orquestra o lote item a item; agrupamento é
   apresentação (JS); quarentena/zip/manifest/restore moram no Python.
5. **Quarentena guarda só a última execução**, compactada em zip.

## Fluxo novo (GUI)

`welcome → scan → review → plan → executing → done` + tela utilitária
`quarantine` (acessível pela barra lateral a qualquer momento).

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

Removidos / falharam / pulados, com o destino (quarentena) e botão
"Abrir quarentena".

### Tela Quarentena

Mostra a última execução: data, itens (nome + caminho original + tamanho),
tamanho do zip. Botões: **Restaurar tudo** (each: se o caminho de origem já
existe, pula com aviso no feed; senão extrai de volta e remove a entrada) e
**Esvaziar** (hard delete do zip+manifesto — único ponto de apagamento
definitivo da GUI). Sem quarentena: estado vazio explicativo.

## Motor (Python)

### `summaryPlain` no payload

Novo campo por candidato em `to_report_payload` e no `OrphanCandidate`:
uma frase em pt-BR derivada das evidências dominantes (ex.: "não está na
lista de programas instalados do Windows, mas ainda há pastas dele no
sistema"). Mapa fixo evidência→frase na mesma fonte dos textos de scoring;
evidências técnicas continuam em `evidences` (contrato `--json` do CLI
ganha o campo novo sem remover nada — aditivo, retrocompatível).

### `quarantine.py` (novo módulo)

- layout: `%LOCALAPPDATA%\Vector\quarantine\` com `staging\` durante a
  execução, `backup.zip` + `manifest.json` selados. Entradas do zip:
  `<id>/<caminho relativo>`; `manifest.json`: lista
  `{id, original, archived, size_bytes, ts}` + `sealed_ts`.
- `stage(candidate)` — move a pasta inteira para o staging (shutil.move);
  PermissionError vira falha reportada, nunca traceback.
- `seal()` — compacta staging em `backup.zip` (ZIP_DEFLATED), escreve
  manifesto, **substitui** (apaga) zip/manifesto/staging anteriores.
  Idempotente; se staging existe e não foi selado (queda de energia),
  `info()` chama `seal()` primeiro (nunca se perdem itens).
- `info()` / `restore_all()` / `purge()` — usados pelos comandos do bridge.
- Sem dependências novas (zipfile/pathlib/shutil da stdlib).

### Bridge — comandos novos

`remove` passa a mover para a quarentena (assinatura/resposta iguais, com
`quarantined: true` + `sizeBytes`); novos: `quarantine-info`,
`quarantine-seal`, `quarantine-restore`, `quarantine-purge`. O guard atual
(HIGH/MEDIUM only, só pasta, não-allowlisted, revalidação contra o report
em memória) vale para todo `remove` do lote, inalterado. CLI `--clean`
interativo do terminal mantém hard delete (comportamento auditado à parte;
a GUI é o produto com quarentena).

## Host (VectorHost.ps1)

Novos repasses de mensagem (`quarantine-*` → `Invoke-Engine` → resposta ao
JS), sem regra nenhuma aqui. Sem mudança no modelo síncrono 1:1.

## Fora de escopo (YAGNI)

Restauração seletiva item a-item na GUI · retenção de mais de uma execução ·
criptografia do zip · tela de configurações.

## Testes

- `test_quarantine.py`: stage/seal/restore/purge com tmp_path (inclui:
  restore com destino já existente pula; seal substitui execução anterior;
  staging órfão é selado por info()).
- `test_bridge.py`: novos comandos + `remove` quarentenando (remove_fn
  injetado) + `summaryPlain` presente no payload de scan.
- GUI: mock.js ganha candidatos com `summaryPlain` e a mesma estrutura de
  seções; fluxo completo revisável no preview do browser antes do rebuild
  do exe.
