#Requires -Version 5.1
<#
    Builds gui/Vector.ico (multi-resolution: 16/32/48/256) drawing the
    Vector mark directly with GDI+ (.NET only, no browser/ImageMagick).

    The mark is the same geometry as gui/vector/assets/vector-mark.svg
    (crosshair + scalpel slash, Vector magenta) on the app's dark field.
    Small sizes deliberately SIMPLIFY: at 16/32px the dashed inner ring is
    dropped and strokes thicken, because a 64px-grid mark copied 1:1 into
    16px turns into mud. Size-adaptive icon drawing, not a blind resize.

    Modern .ico files can embed PNG-encoded frames directly, which is all
    this does - draw each size and staple them with a hand-written
    ICONDIR header (same approach as genesis/scripts/make-exe-icon.ps1).
#>

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$Root = Split-Path -Parent $PSScriptRoot
$outIco = Join-Path $Root 'gui\Vector.ico'

# Paleta do Vector (DESIGN.md): fundo #14060f, anel #EC4899, detalhes #F9A8D4.
$bgColor = [System.Drawing.ColorTranslator]::FromHtml('#14060f')
$ringColor = [System.Drawing.ColorTranslator]::FromHtml('#EC4899')
$slashColor = [System.Drawing.ColorTranslator]::FromHtml('#F9A8D4')

$sizes = 16, 32, 48, 256
$pngBlobs = @()

foreach ($sizeItem in $sizes) {
    $size = [int]$sizeItem
    $bmp = New-Object System.Drawing.Bitmap $size, $size
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic

    # fundo: quadrado arredondado na cor do campo do app (legivel na
    # barra de tarefas clara ou escura).
    $radius = [Math]::Max(2, [int]($size * 0.22))
    $rectSize = $size - 1
    $rect = New-Object System.Drawing.Rectangle(0, 0, $rectSize, $rectSize)
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $radius * 2
    $path.AddArc($rect.X, $rect.Y, $d, $d, 180, 90)
    $path.AddArc($rect.Right - $d, $rect.Y, $d, $d, 270, 90)
    $path.AddArc($rect.Right - $d, $rect.Bottom - $d, $d, $d, 0, 90)
    $path.AddArc($rect.X, $rect.Bottom - $d, $d, $d, 90, 90)
    $path.CloseFigure()
    $g.FillPath((New-Object System.Drawing.SolidBrush($bgColor)), $path)

    # escala: a marca foi desenhada numa grade 64x64.
    $scale = $size / 64.0
    $center = $size / 2.0

    # simplificacao por tamanho: 16/32px sem anel interno tracejado e
    # com tracos mais grossos (a versao 1:1 em 16px vira lama).
    $isSmall = $size -le 32
    $ringStroke = if ($isSmall) { [Math]::Max(1, [int](3.5 * $scale * 1.6)) } else { [Math]::Max(1, [int](3.5 * $scale)) }
    $tickStroke = if ($isSmall) { [Math]::Max(1, [int](3.0 * $scale * 1.6)) } else { [Math]::Max(1, [int](3.0 * $scale)) }
    $slashStroke = if ($isSmall) { [Math]::Max(1, [int](3.5 * $scale * 1.6)) } else { [Math]::Max(1, [int](3.5 * $scale)) }

    $ringPen = New-Object System.Drawing.Pen($ringColor, $ringStroke)
    $slashPen = New-Object System.Drawing.Pen($slashColor, $slashStroke)
    $slashPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $slashPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round

    # anel externo
    $ringRect = New-Object System.Drawing.RectangleF(
        ($center - 22 * $scale), ($center - 22 * $scale), (44 * $scale), (44 * $scale))
    $g.DrawEllipse($ringPen, $ringRect)

    # anel interno tracejado (so nos tamanhos grandes)
    if (-not $isSmall) {
        $innerPen = New-Object System.Drawing.Pen($slashColor, [Math]::Max(1, [int](2.0 * $scale)))
        $innerPen.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dash
        $innerRect = New-Object System.Drawing.RectangleF(
            ($center - 13 * $scale), ($center - 13 * $scale), (26 * $scale), (26 * $scale))
        $g.DrawEllipse($innerPen, $innerRect)
        $innerPen.Dispose()
    }

    # ticks da mira (N/S/L/O)
    $tickPen = New-Object System.Drawing.Pen($ringColor, $tickStroke)
    $tickPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $tickPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $gapIn = 24 * $scale
    $gapOut = 34 * $scale
    $g.DrawLine($tickPen, $center, ($center - $gapOut), $center, ($center - $gapIn))
    $g.DrawLine($tickPen, $center, ($center + $gapIn), $center, ($center + $gapOut))
    $g.DrawLine($tickPen, ($center - $gapOut), $center, ($center - $gapIn), $center)
    $g.DrawLine($tickPen, ($center + $gapIn), $center, ($center + $gapOut), $center)

    # corte cirurgico (barra diagonal 22,42 -> 42,22 na grade 64)
    $g.DrawLine($slashPen,
        ($center - 10 * $scale), ($center + 10 * $scale),
        ($center + 10 * $scale), ($center - 10 * $scale))

    $tickPen.Dispose()
    $slashPen.Dispose()
    $ringPen.Dispose()
    $path.Dispose()
    $g.Dispose()

    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $pngBlobs += , $ms.ToArray()

# ICONDIR (6 bytes) + um ICONDIRENTRY (16 bytes) por imagem, depois os PNGs.
$headerSize = 6
$entrySize = 16
$offset = $headerSize + ($entrySize * $sizes.Count)

$stream = New-Object System.IO.MemoryStream
$writer = New-Object System.IO.BinaryWriter($stream)

$writer.Write([uint16]0)      # reservado
$writer.Write([uint16]1)      # tipo: 1 = icone
$writer.Write([uint16]$sizes.Count)

for ($i = 0; $i -lt $sizes.Count; $i++) {
    $size = $sizes[$i]
    $blob = $pngBlobs[$i]
    $byteSize = if ($size -eq 256) { 0 } else { $size }  # 256 encoda como 0 no spec
    $writer.Write([byte]$byteSize)
    $writer.Write([byte]$byteSize)
    $writer.Write([byte]0)
    $writer.Write([byte]0)
    $writer.Write([uint16]1)
    $writer.Write([uint16]32)
    $writer.Write([uint32]$blob.Length)
    $writer.Write([uint32]$offset)
    $offset += $blob.Length
}
foreach ($blob in $pngBlobs) { $writer.Write($blob) }

$writer.Flush()
[System.IO.File]::WriteAllBytes($outIco, $stream.ToArray())
$writer.Dispose()
$stream.Dispose()

Write-Host "Gerado: $outIco ($($sizes -join '/')px)" -ForegroundColor Green

    $ms.Dispose()
    $bmp.Dispose()
}

