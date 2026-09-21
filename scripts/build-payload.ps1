#Requires -Version 5.1
<#
    Gera .build/payload.ps1 - o pacote embutido do Vector.exe.

    O Vector.exe compilado e um arquivo UNICO: ele nao precisa de gui/ do
    lado dele. Este script junta tudo o que a interface precisa em tempo de
    execucao num zip, comprime (gzip) e grava como base64 num here-string
    do PowerShell. O build.ps1 injeta esse arquivo + gui/VectorHost.ps1
    pra compilar o exe (a extracao em runtime e o Expand-VectorPayload,
    dentro do proprio VectorHost.ps1).

    Ficam FORA do payload: probe/capturas de desenvolvimento, caches e
    bytecode.
#>

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$OutDir = Join-Path $Root '.build'
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

# Pastas inteiras embutidas (caminhos relativos a raiz do projeto).
# Fase 2: 'src' carrega o motor Python (vector.bridge) dentro do exe; o
# VectorHost.ps1 o executa via `python vector-cli.py --serve` na pasta extraida.
$includeDirs = @(
    'gui\vector',
    'src'
)

# Arquivos soltos que o host usa direto na raiz de $Root.
$includeFiles = @(
    # gui/Vector.ico: o VectorHost.ps1 carrega como $form.Icon na abertura
    # (e o que a barra de tarefas mostra - o -iconFile do ps2exe so marca o
    # arquivo .exe no Explorer).
    'gui\Vector.ico',
    # entry-point fino: fica ao lado de src/ na pasta extraida, e o VectorHost
    # chama `python vector-cli.py --serve` (ele mesmo insere src/ no sys.path).
    'vector-cli.py'
)

$exclude = '__pycache__|\.pyc$|^\.probe|^\.shot|^\.dom|^\.clean-|\.verify|\.edge-err'

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$tmpZip = Join-Path $OutDir 'payload.zip'
if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force }

$count = 0
$archive = [System.IO.Compression.ZipFile]::Open($tmpZip, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    $add = {
        param([string]$FullPath)
        # dentro do zip o caminho e sempre relativo a raiz, com barras "/"
        $entry = $FullPath.Substring($Root.Length + 1) -replace '\\', '/'
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, $FullPath, $entry, [System.IO.Compression.CompressionLevel]::Optimal)
        $script:count++
    }

    foreach ($rel in $includeDirs) {
        $dir = Join-Path $Root $rel
        if (-not (Test-Path $dir)) { throw "Pasta obrigatoria nao encontrada: $rel" }
        Get-ChildItem -Path $dir -Recurse -File -Force |
            Where-Object { $_.FullName -notmatch $exclude -and $_.Name -notmatch '^\.|^dev\.(cmd|ps1)$' } |
            ForEach-Object { & $add $_.FullName }
    }

    foreach ($rel in $includeFiles) {
        $file = Join-Path $Root $rel
        if (Test-Path $file) { & $add $file }
        else { Write-Warning "Arquivo opcional ausente, ficando fora do payload: $rel" }
    }
}
finally { $archive.Dispose() }

# zip -> gzip -> base64 (o exe carrega isso como texto puro)
$zipBytes = [System.IO.File]::ReadAllBytes($tmpZip)
$gzipStream = New-Object System.IO.MemoryStream
$gzip = New-Object System.IO.Compression.GZipStream($gzipStream, [System.IO.Compression.CompressionMode]::Compress, $true)
$gzip.Write($zipBytes, 0, $zipBytes.Length)
$gzip.Dispose()
$base64 = [Convert]::ToBase64String($gzipStream.ToArray())
$gzipStream.Dispose()

# A versao e o hash do proprio payload: muda o conteudo, muda a pasta de
# cache em runtime (%LOCALAPPDATA%\Vector\app\<versao>).
$sha = [System.Security.Cryptography.SHA256]::Create()
$digest = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($base64))
$version = (($digest | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0, 16)

$payloadFile = Join-Path $OutDir 'payload.ps1'
$text = @"
# Gerado por scripts/build-payload.ps1 - NAO versionado, NAO edite a mao.
# $count arquivos embutidos (zip + base64), versao $version.
`$Global:VectorPayloadVersion = '$version'
`$Global:VectorPayloadBase64 = @'
$base64
'@
"@
[System.IO.File]::WriteAllText($payloadFile, $text, (New-Object System.Text.UTF8Encoding($true)))
Remove-Item $tmpZip -Force

$kb = [math]::Round((Get-Item $payloadFile).Length / 1KB)
Write-Host "Payload: $count arquivos, $kb KB em base64 -> $payloadFile (versao $version)" -ForegroundColor Green
