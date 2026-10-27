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

    $zimFiles = Get-ChildItem -Path $ZimDir -Filter "*.zim" -File -ErrorAction SilentlyContinue
    $presentNames = @{}
    foreach ($z in $zimFiles) {
        $presentNames[$z.Name.ToLowerInvariant()] = $true
    }

    [xml]$xml = Get-Content -Path $TemplateXmlPath -Raw -Encoding UTF8
    $root = $xml.library
    $nodesToRemove = @()

    foreach ($book in $root.book) {
        $pathAttr = $book.GetAttribute("path")
        $fileName = [System.IO.Path]::GetFileName($pathAttr).ToLowerInvariant()
        if (-not $presentNames.ContainsKey($fileName)) {
            $nodesToRemove += $book
        }
    }

    foreach ($node in $nodesToRemove) {
        [void]$root.RemoveChild($node)
    }

    $outDir = [System.IO.Path]::GetDirectoryName($OutputXmlPath)
    if ($outDir -and -not (Test-Path $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }

    $settings = New-Object System.Xml.XmlWriterSettings
    $settings.Indent = $true
    $settings.IndentChars = "  "
    $settings.Encoding = [System.Text.Encoding]::UTF8

    $writer = [System.Xml.XmlWriter]::Create($OutputXmlPath, $settings)
    $xml.Save($writer)
    $writer.Close()

    $retainedCount = $root.book.Count
    return $retainedCount
}

if ($MyInvocation.MyCommand.ModuleName) {
    Export-ModuleMember -Function Build-LibraryXml -ErrorAction SilentlyContinue
}
