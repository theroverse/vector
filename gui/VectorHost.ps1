#Requires -Version 5.1
<#
    Native shell for the Vector interface: a borderless WinForms window
    hosting a WebView2 control pointed at gui/vector/index.html. The
    HTML/CSS/JS is the whole UI (see gui/vector/) - this file only owns
    the window chrome, the elevation, the payload extraction and the
    JS <-> PowerShell message bridge.

    PHASE 1 (today): the interface renders representative example data
    (gui/vector/mock.js) so the look and the flow can be approved before
    anything touches the real machine. The engine commands below
    ('start-scan', 'remove-folder') are deliberate, documented stubs that
    answer 'not-implemented'.

    PHASE 2: those two handlers call the real Python engine
    (src/vector/engine.py) - run_scan() for the evidence tree and the
    same guarded removal path as vector-cli.py --clean. Scoring and
    safety rules live in Python and must not be reimplemented here.

    Message protocol (JSON, one object per message):
      JS -> PS : { type: 'ready' | 'window-close' | 'window-minimize'
                        | 'window-drag' | 'start-scan' | 'remove-folder',
                   payload: <anything the handler needs> }
      PS -> JS : { type: 'host-ready' | 'not-implemented' | 'bridge-error',
                   payload: <...> }
#>

param([switch]$SkipElevationCheck)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# ------------------------------------------------------------------ payload --
<#
    Vector.exe compilado e um arquivo UNICO: gui/ entra embutido em base64
    (ver scripts/build-payload.ps1) e e extraido em
    %LOCALAPPDATA%\Vector\app\<versao> na primeira execucao. Rodando direto
    da pasta do projeto (dev, sem compilar) nao ha payload e $Root e a
    propria pasta do projeto. Mesma mecanica do genesis/GenesisBootstrap.ps1.
#>
function Expand-VectorPayload {
    param(
        [Parameter(Mandatory)][string]$ExeDir,
        [string]$PayloadBase64 = $Global:VectorPayloadBase64,
        [string]$PayloadVersion = $Global:VectorPayloadVersion
    )

    if (-not $PayloadBase64) { return $ExeDir }
    if (-not $PayloadVersion) { $PayloadVersion = 'dev' }

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $cacheRoot = Join-Path $env:LOCALAPPDATA 'Vector\app'
    $target = Join-Path $cacheRoot $PayloadVersion

    # gui/vector/app.js como sentinela: se nao esta la, a extracao nao
    # terminou (ou a pasta foi limpa) e o payload precisa ser descompactado.
    if (-not (Test-Path (Join-Path $target 'gui\vector\app.js'))) {
        New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null

        $gzipBytes = [Convert]::FromBase64String($PayloadBase64)
        $input = New-Object System.IO.MemoryStream
        $input.Write($gzipBytes, 0, $gzipBytes.Length)
        $input.Position = 0
        $gzip = New-Object System.IO.Compression.GZipStream($input, [System.IO.Compression.CompressionMode]::Decompress)
        $zipStream = New-Object System.IO.MemoryStream
        $gzip.CopyTo($zipStream)
        $gzip.Dispose()
        $input.Dispose()

        # extrai numa pasta temporaria e so depois promove: nada de cache
        # pela metade se algo falhar no meio.
        $staging = "$target.tmp"
        if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
        New-Item -ItemType Directory -Path $staging -Force | Out-Null

        $tmpZip = Join-Path $cacheRoot 'payload.zip'
        [System.IO.File]::WriteAllBytes($tmpZip, $zipStream.ToArray())
        $zipStream.Dispose()
        try {
            [System.IO.Compression.ZipFile]::ExtractToDirectory($tmpZip, $staging)
        }
        finally {
            Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
        }

        Get-ChildItem $cacheRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne $PayloadVersion -and $_.Name -notlike '*.tmp' } |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $target) { Remove-Item $target -Recurse -Force -ErrorAction SilentlyContinue }
        Move-Item -Path $staging -Destination $target -Force
    }

    return $target
}

# --------------------------------------------------------------------- boot --
# Dois modos de execucao:
#   - script (.ps1): rodar direto da pasta do projeto, sem compilar nada.
#   - exe (ps2exe):   o MainModule e o proprio Vector.exe, e nesse caso o
#                     payload embutido e extraido pra %LOCALAPPDATA%.
$script:IsScript = [bool]$PSCommandPath
$exeFullPath = [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
$exeBaseName = [System.IO.Path]::GetFileNameWithoutExtension($exeFullPath)

if ($PSCommandPath -and $exeBaseName -match '^(powershell|pwsh)$') {
    $ExeDir = Split-Path -Parent $PSCommandPath
    $Root = $ExeDir
}
else {
    $ExeDir = Split-Path -Parent $exeFullPath
    $Root = Expand-VectorPayload -ExeDir $ExeDir
}

$indexPath = Join-Path $Root 'gui\vector\index.html'
$iconPath = Join-Path $Root 'gui\Vector.ico'

# Elevacao ANTES de qualquer UI: sem admin o scan nao enxerga boa parte de
# Program Files / ProgramData e o relatorio sairia incompleto. Relanca
# elevado e sai; o filho elevado entra com -SkipElevationCheck.
if (-not $SkipElevationCheck) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        if ($script:IsScript) {
            Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-SkipElevationCheck'
            )
        }
        else {
            Start-Process -FilePath $exeFullPath -Verb RunAs -ArgumentList @('-SkipElevationCheck')
        }
        exit
    }
}


# --- native drag + rounded corners (Windows 11) -----------------------------
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class NativeDrag {
    [DllImport("user32.dll")] public static extern bool ReleaseCapture();
    [DllImport("user32.dll")] public static extern int SendMessage(IntPtr hWnd, int Msg, int wParam, int lParam);
    [DllImport("dwmapi.dll")] public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
    public const int WM_NCLBUTTONDOWN = 0xA1;
    public const int HTCAPTION = 0x2;
    public const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
    public const int DWMWCP_ROUND = 2;
    // Assinatura com IntPtr (nao Forms.Form): Add-Type sem
    // -ReferencedAssemblies nao compila tipos de System.Windows.Forms e o
    // Add-Type inteiro falharia, matando tambem o drag da titlebar.
    public static void RoundCorners(IntPtr hwnd) {
        try {
            int pref = DWMWCP_ROUND;
            DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ref pref, 4);
        }
        catch { }
    }
}
'@

# ------------------------------------------------------------------ window --
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Vector'
$form.Size = New-Object System.Drawing.Size(1180, 780)
$form.MinimumSize = New-Object System.Drawing.Size(900, 620)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'None'
$form.BackColor = [System.Drawing.ColorTranslator]::FromHtml('#14060f')
if (Test-Path $iconPath) {
    try { $form.Icon = New-Object System.Drawing.Icon($iconPath) } catch { }
}

# Trap cobrindo tudo do $Root pra baixo: um erro terminante nesse trecho
# (payload corrompido, runtime do WebView2 ausente) matava o processo sem
# aviso nenhum - sem MessageBox, sem log. "break" para o processo ali em
# vez de continuar com estado pela metade.
trap {
    $crashMsg = "Vector falhou ao iniciar:`n`n$($_.Exception.Message)`n`n$($_.ScriptStackTrace)"
    try {
        $logDir = Join-Path $env:LOCALAPPDATA 'Vector\logs'
        New-Item -ItemType Directory -Path $logDir -Force -ErrorAction SilentlyContinue | Out-Null
        $crashMsg | Out-File (Join-Path $logDir "crash-startup-$(Get-Date -Format 'yyyyMMdd-HHmmss').log") -Encoding utf8
    }
    catch { }
    [System.Windows.Forms.MessageBox]::Show($crashMsg, 'Vector', 'OK', 'Error')
    break
}

if (-not (Test-Path $indexPath)) {
    [System.Windows.Forms.MessageBox]::Show(
        "Nao encontrei a interface em:`n$indexPath`n`nRode a partir da pasta do projeto (gui\VectorHost.ps1) ou recompile com build.ps1.",
        'Vector', 'OK', 'Error')
    exit 1
}

$webView = New-Object Microsoft.Web.WebView2.WinForms.WebView2
$webView.Dock = 'Fill'
$webView.DefaultBackgroundColor = [System.Drawing.ColorTranslator]::FromHtml('#14060f')

# Sem isso, o init preguicoso do WebView2 cria uma pasta
# "<nome do exe>.WebView2" DO LADO DO exe (cache, cookies) na primeira
# execucao - sujeira na pasta de instalacao. Definir CreationProperties
# antes da primeira navegacao redireciona esses dados pro AppData do
# usuario, como qualquer outro app.
$creationProps = New-Object Microsoft.Web.WebView2.WinForms.CoreWebView2CreationProperties
$creationProps.UserDataFolder = Join-Path $env:LOCALAPPDATA 'Vector\WebView2'
$webView.CreationProperties = $creationProps

$form.Controls.Add($webView)
$form.Add_Shown({ [NativeDrag]::RoundCorners($form.Handle) })


# ------------------------------------------------------------------ bridge --
# [array] cast: veja o comentario longo no genesis/gui/WizardHost.ps1 -
# qualquer array entregue ao -Payload vira propriedade ANINHADA do wrapper
# abaixo, que e exatamente onde o ConvertTo-Json do Windows PowerShell 5.1
# transforma um array puro em {"value":[...],"Count":N} em vez de [...].
function Send-ToJs {
    param([string]$Type, $Payload)
    if (($Payload -is [array] -or $Payload -is [System.Collections.ICollection]) -and
        $Payload -isnot [System.Collections.IDictionary]) {
        $Payload = [array]$Payload
    }
    $msg = @{ type = $Type; payload = $Payload } | ConvertTo-Json -Depth 8 -Compress
    $webView.CoreWebView2.PostWebMessageAsJson($msg)
}

function Handle-Message {
    param($Msg)

    switch ($Msg.type) {
        'ready' {
            # A interface avisou que carregou; confirma o host e o modo.
            Send-ToJs -Type 'host-ready' -Payload @{
                app = 'vector'
                phase = 'mock'
                root = $Root
                notice = 'Fase 1: dados de exemplo. O motor real (src/vector) e ligado na fase 2.'
            }
        }
        'window-close' {
            # A limpeza pode estar no meio de um fluxo de confirmacao.
            if ($Msg.payload -and $Msg.payload.confirm) {
                $result = [System.Windows.Forms.MessageBox]::Show(
                    $form, 'Tem certeza que quer fechar o Vector?', 'Vector',
                    'YesNo', 'Question')
                if ($result -ne [System.Windows.Forms.DialogResult]::Yes) { return }
            }
            $form.Close()
        }
        'window-minimize' { $form.WindowState = 'Minimized' }
        'window-drag' {
            [NativeDrag]::ReleaseCapture() | Out-Null
            [NativeDrag]::SendMessage($form.Handle, [NativeDrag]::WM_NCLBUTTONDOWN, [NativeDrag]::HTCAPTION, 0) | Out-Null
        }
        'start-scan' {
            # FASE 2: chamar o motor Python real (src/vector/engine.py,
            # run_scan) num runspace de fundo e empurrar o ScanReport por
            # 'scan-result'. Hoje responde com clareza que ainda nao esta
            # ligado - a interface usa os dados de exemplo (mock.js).
            Send-ToJs -Type 'not-implemented' -Payload @{
                command = 'start-scan'
                reason = 'Fase 2: o motor real (src/vector/engine.py) ainda nao esta ligado nesta janela.'
                fallback = 'mock'
            }
        }
        'remove-folder' {
            # FASE 2: mesma trilha de remocao do vector-cli.py --clean
            # (digitacao literal + confirmacao, allowlist, sem registro/
            # servico/tarefa). NUNCA remover sem o mesmo guard do CLI.
            Send-ToJs -Type 'not-implemented' -Payload @{
                command = 'remove-folder'
                reason = 'Fase 2: a remocao real exige o guard do vector-cli.py --clean.'
                fallback = 'mock'
            }
        }
        default {
            Send-ToJs -Type 'bridge-error' -Payload @{
                error = "Mensagem desconhecida: $($Msg.type)"
            }
        }
    }
}

# --------------------------------------------------------------------- wire --
$webView.add_CoreWebView2InitializationCompleted({
    param($s, $e)
    if (-not $e.IsSuccess) {
        # 0x800700AA = ERROR_BUSY: a pasta de dados do WebView2
        # (%LOCALAPPDATA%\Vector\WebView2) esta travada por OUTRA instancia
        # do Vector (ou copia dele) ainda aberta - nao e falta de runtime,
        # so nao dava pra saber isso da mensagem generica de baixo.
        $msg = if ($e.InitializationException.HResult -eq -2147024726) {
            "Ja existe outra instancia do Vector aberta (ou travada em segundo plano).`n`nFeche-a (Gerenciador de Tarefas, se preciso) e abra o Vector de novo."
        }
        else {
            "WebView2 nao inicializou: $($e.InitializationException.Message)`n`nO Runtime do WebView2 (vem com o Windows 11) pode estar faltando."
        }
        [System.Windows.Forms.MessageBox]::Show($msg, 'Vector', 'OK', 'Error')
        $form.Close()
        return
    }
    $webView.CoreWebView2.add_WebMessageReceived({
        # NUNCA nomear este 2o parametro de $args: o PowerShell ja tem a
        # variavel automatica $args, e sombrear aqui fez o objeto real
        # CoreWebView2WebMessageReceivedEventArgs chegar como Object[] -
        # exatamente o bug "does not contain a method named
        # TryGetWebMessageAsString" (aprendido no Genesis).
        param($sender, $webMsgArgs)
        try {
            $json = $webMsgArgs.TryGetWebMessageAsString()
            $msg = $json | ConvertFrom-Json
            Handle-Message -Msg $msg
        }
        catch {
            Send-ToJs -Type 'bridge-error' -Payload @{
                error = $_.Exception.Message
            }
        }
    })
})
$webView.Source = [Uri]::new($indexPath)

[void]$form.ShowDialog()

