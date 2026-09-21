#Requires -Version 5.1
<#
    Compila o Vector.exe a partir do codigo-fonte, usando o modulo ps2exe.

    O resultado e UM ARQUIVO SO: gui/vector/ e gui/Vector.ico entram
    embutidos num payload comprimido (gerado por scripts/build-payload.ps1)
    e sao extraidos em %LOCALAPPDATA%\Vector\app\<versao> na primeira
    execucao - quem faz isso e o Expand-VectorPayload dentro do
    gui/VectorHost.ps1. Ou seja: da pra copiar o Vector.exe sozinho, pra
    qualquer pasta, sem levar nada junto.

    O exe sai em dist/ (isolado, longe das fontes) para provar que ele roda
    sem nenhum arquivo extra por perto.

    FASE 1: a interface roda com dados de exemplo (mock). FASE 2: acrescentar
    'src' ao payload em scripts/build-payload.ps1 liga o motor Python real.

    Passos daqui:
      1. gera .build/payload.ps1 (todos os assets: zip -> gzip -> base64)
      2. monta .build/Vector.ps1 = payload (base64, lido em runtime) + host
      3. compila esse script unico em dist/Vector.exe

    Rodar direto da pasta do projeto continua valendo, sem compilar nada:
    .\gui\VectorHost.ps1 (janela) e .\gui\vector\dev.cmd (preview no browser).
#>

$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
$OutDir = Join-Path $Root 'dist'
$OutExe = Join-Path $OutDir 'Vector.exe'
$BuildDir = Join-Path $Root '.build'

if (-not (Get-PackageProvider -Name NuGet -ListAvailable -ErrorAction SilentlyContinue)) {
    Write-Host "Instalando provedor NuGet (necessario pro PowerShellGet baixar modulos)..." -ForegroundColor Cyan
    Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force | Out-Null
}

if (-not (Get-Module -ListAvailable -Name ps2exe)) {
    Write-Host "Instalando modulo ps2exe..." -ForegroundColor Cyan
    Install-Module -Name ps2exe -Scope CurrentUser -Force -AllowClobber
}
Import-Module ps2exe

$iconFile = Join-Path $Root 'gui\Vector.ico'
if (-not (Test-Path $iconFile)) {
    Write-Host "Icone nao encontrado, gerando..." -ForegroundColor Cyan
    & (Join-Path $Root 'scripts\make-exe-icon.ps1')
}

# 1) payload embutido --------------------------------------------------------
Write-Host "`n[1/3] Gerando o payload embutido..." -ForegroundColor Cyan
& (Join-Path $Root 'scripts\build-payload.ps1')

# 2) script unico = payload (dados) + host -----------------------------------
# O payload.ps1 NAO e concatenado como codigo: ele e lido aqui como TEXTO,
# convertido pra base64 (linha unica, sem aspas) e avaliado em runtime via
# [ScriptBlock]::Create, DEPOIS que as funcoes ja existem. Dois motivos:
#   a) o VectorHost.ps1 tem um bloco param() que so e valido no topo do
#      script - concatenado atras do payload, ele virava o "O termo 'param'
#      nao e reconhecido" e matava o exe na abertura;
#   b) o payload.ps1 contem a linha terminadora '@ (do proprio here-string
#      dele) - embuti-lo dentro de outro here-string quebraria o parse.
Write-Host "[2/3] Montando o script unico do exe..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
$singleScript = Join-Path $BuildDir 'Vector.ps1'
$payloadFile = Join-Path $BuildDir 'payload.ps1'
$hostFile = Join-Path $Root 'gui\VectorHost.ps1'

foreach ($part in @($payloadFile, $hostFile)) {
    if (-not (Test-Path $part)) { throw "Parte do script unico nao encontrada: $part" }
}
# ReadAllText(UTF8) ja descarta o BOM: o texto avaliado em runtime comeca
# limpo, e cada parte entra sem BOM no arquivo final (so ele leva BOM).
$payloadSource = [System.IO.File]::ReadAllText($payloadFile, [System.Text.Encoding]::UTF8)
$payloadB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($payloadSource))
$single = New-Object System.Text.StringBuilder
[void]$single.AppendLine('# Gerado pelo build.ps1 - NAO edite. O payload vai EMBUTIDO abaixo em')
[void]$single.AppendLine('# base64 e e avaliado em runtime, NAO como codigo (ver comentario no build).')
[void]$single.AppendLine('$__VectorPayloadB64 = ''')
[void]$single.AppendLine($payloadB64)
[void]$single.AppendLine('''')
[void]$single.AppendLine('$__VectorPayloadSource = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($__VectorPayloadB64))')
[void]$single.AppendLine('. ([ScriptBlock]::Create($__VectorPayloadSource))')
[void]$single.AppendLine('Remove-Variable -Name __VectorPayloadB64, __VectorPayloadSource -Scope Script -ErrorAction SilentlyContinue')

# Do host entra tudo, menos o bloco param() do topo (so e valido como
# primeiro comando do script - concatenado atras do payload virava o
# 'O termo param nao e reconhecido' que matava o exe na abertura). Ele vira
# uma leitura de $args, que o ps2exe repassa do exe pro script: sem admin,
# relanca com -SkipElevationCheck, e o filho elevado pula a checagem.
$hostText = [System.IO.File]::ReadAllText($hostFile, [System.Text.Encoding]::UTF8)
$skipReplacement = '$SkipElevationCheck = [bool]$args.Count'
$hostBody = $hostText -replace '(?m)^param\(\[switch\]\$SkipElevationCheck\)\s*\r?$', $skipReplacement
[void]$single.AppendLine($hostBody)
[System.IO.File]::WriteAllText($singleScript, $single.ToString(), (New-Object System.Text.UTF8Encoding($true)))

# 3) compila -----------------------------------------------------------------
# ps2exe escreve o .win32manifest AO LADO do exe de saida: sem a pasta dist/
# criada antes, ele morre com "Nao foi possivel localizar uma parte do caminho".
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
Write-Host "[3/3] Compilando com ps2exe (pode demorar um pouco)..." -ForegroundColor Cyan
# ps2exe substitui o exe de saida. Apagar um .exe recem-gerado as vezes e
# negado pelo Windows (handle de antivirus/indexer) MESMO sem ninguem
# usando: por isso o delete aqui e via [System.IO.File]::Delete.
if (Test-Path $OutExe) {
    try { [System.IO.File]::Delete((Resolve-Path $OutExe)) }
    catch {
        Write-Warning "Nao deu pra apagar o Vector.exe atual ($($_.Exception.Message)). Feche o exe se estiver aberto e rode o build de novo."
    }
}
Invoke-ps2exe `
    -inputFile $singleScript `
    -outputFile $OutExe `
    -iconFile $iconFile `
    -title 'Vector' `
    -description 'Vector - limpeza cirurgica de residuos de programas' `
    -company 'Anthero' `
    -product 'Vector - limpeza cirurgica' `
    -version '1.0.0.0' `
    -noConsole `
    -requireAdmin `
    -x64

if (-not (Test-Path $OutExe)) {
    throw "ps2exe rodou mas $OutExe nao foi criado - veja a saida acima pro erro real."
}

$size = [math]::Round((Get-Item $OutExe).Length / 1MB, 1)
Write-Host "`nGerado: $OutExe ($size MB)" -ForegroundColor Green
Write-Host "Arquivo unico em dist/: pode copiar o .exe sozinho pra qualquer pasta." -ForegroundColor Yellow
Write-Host "Ele extrai o proprio payload em %LOCALAPPDATA%\Vector\app\<versao> na primeira execucao." -ForegroundColor Yellow


