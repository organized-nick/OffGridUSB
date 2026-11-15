<#
.SYNOPSIS
    LibraryXmlBuilder - Dynamic Kiwix library.xml builder in pure PowerShell.
#>

[CmdletBinding()]
param()

function Build-LibraryXml {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ZimDir,

        [Parameter(Mandatory = $true)]
        [string]$TemplateXmlPath,

        [Parameter(Mandatory = $true)]
        [string]$OutputXmlPath
    )

    if (-not (Test-Path $ZimDir)) {
        throw "ZIM directory not found: $ZimDir"
    }
    if (-not (Test-Path $TemplateXmlPath)) {
        throw "Template library.xml not found: $TemplateXmlPath"
    }

    $zimFiles = @(Get-ChildItem -Path $ZimDir -Filter "*.zim" -File -ErrorAction SilentlyContinue | Sort-Object Name)
    $presentNames = @{}
    foreach ($z in $zimFiles) {
        $presentNames[$z.Name.ToLowerInvariant()] = $z
    }

    # Optional catalog metadata lookup from manifests/zim.json
    $catalogByFile = @{}
    $repoRoot = Split-Path -Parent (Split-Path -Parent $TemplateXmlPath)
    $zimJsonPath = Join-Path $repoRoot "manifests\zim.json"
    if (Test-Path $zimJsonPath) {
        try {
            $zimManifest = Get-Content -Path $zimJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($entry in $zimManifest.archives) {
                if ($entry.filename) {
                    $catalogByFile[$entry.filename.ToLowerInvariant()] = $entry
                }
            }
        } catch {
            # Non-fatal fallback to filename-derived metadata
        }
    }

    [xml]$xml = Get-Content -Path $TemplateXmlPath -Raw -Encoding UTF8
    $root = $xml.library
    $nodesToRemove = @()
    $coveredNames = @{}

    foreach ($book in @($root.book)) {
        if (-not $book) { continue }
        $pathAttr = $book.GetAttribute("path")
        $fileName = [System.IO.Path]::GetFileName($pathAttr)
        $fileNameLower = $fileName.ToLowerInvariant()
        if (-not $presentNames.ContainsKey($fileNameLower)) {
            $nodesToRemove += $book
        } else {
            $actualFile = $presentNames[$fileNameLower]
            $book.SetAttribute("path", "zim/$($actualFile.Name)")
            $coveredNames[$fileNameLower] = $true
        }
    }

    foreach ($node in $nodesToRemove) {
        [void]$root.RemoveChild($node)
    }

    # Synthesize valid <book> entries for any staged .zim missing from TemplateXmlPath
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        foreach ($z in $zimFiles) {
            $lower = $z.Name.ToLowerInvariant()
            if ($coveredNames.ContainsKey($lower)) { continue }

            $meta = if ($catalogByFile.ContainsKey($lower)) { $catalogByFile[$lower] } else { $null }
            $hashBytes = $md5.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("offgridusb:" + $lower))
            $bookGuid = ([Guid]::New($hashBytes)).ToString("d")

            $baseNoDate = ($z.BaseName -replace '_\d{4}-\d{2}$', '')
            $dateMatch = [regex]::Match($z.BaseName, '_(\d{4}-\d{2})$')
            $dateStr = if ($dateMatch.Success) { "$($dateMatch.Groups[1].Value)-01" } else { "2026-01-01" }

            $title = if ($meta -and $meta.name) { [string]$meta.name } else { $baseNoDate }
            $desc = if ($meta -and $meta.description) { [string]$meta.description } else { "Offline OpenZIM knowledge archive ($($z.Name))." }
            $catTag = if ($meta -and $meta.category) { [string]$meta.category } else { "knowledge" }
            $bookName = if ($meta -and $meta.id) { [string]$meta.id } else { $baseNoDate }
            $sizeKiB = [math]::Max(1L, [int64][math]::Round($z.Length / 1024.0))

            $newBook = $xml.CreateElement("book")
            $newBook.SetAttribute("id", $bookGuid)
            $newBook.SetAttribute("path", "zim/$($z.Name)")
            $newBook.SetAttribute("title", $title)
            $newBook.SetAttribute("description", $desc)
            $newBook.SetAttribute("language", "eng")
            $newBook.SetAttribute("creator", "openZIM")
            $newBook.SetAttribute("publisher", "openZIM")
            $newBook.SetAttribute("name", $bookName)
            $newBook.SetAttribute("tags", "${catTag};_ftindex:yes;_details:yes")
            $newBook.SetAttribute("date", $dateStr)
            $newBook.SetAttribute("size", "$sizeKiB")
            [void]$root.AppendChild($newBook)
        }
    } finally {
        $md5.Dispose()
    }

    $outDir = [System.IO.Path]::GetDirectoryName($OutputXmlPath)
    if ($outDir -and -not (Test-Path $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }

    $settings = New-Object System.Xml.XmlWriterSettings
    $settings.Indent = $true
    $settings.IndentChars = "  "
    $settings.Encoding = New-Object System.Text.UTF8Encoding($false)

    $writer = [System.Xml.XmlWriter]::Create($OutputXmlPath, $settings)
    $xml.Save($writer)
    $writer.Close()

    $retainedCount = @($root.book).Count
    return $retainedCount
}

if ($MyInvocation.MyCommand.ModuleName) {
    Export-ModuleMember -Function Build-LibraryXml -ErrorAction SilentlyContinue
}
