param(
    [string]$InputPath = "reports/2026-11-24-metrics-1-3-gemini-chatgpt/metrics.md",
    [string]$OutputPath = "reports/2026-11-24-metrics-1-3-gemini-chatgpt/metrics.html"
)

$ErrorActionPreference = "Stop"
$source = (Resolve-Path -LiteralPath $InputPath).Path
$destination = [System.IO.Path]::GetFullPath($OutputPath)
$sourceDirectory = [System.IO.Path]::GetDirectoryName($source)
$body = (ConvertFrom-Markdown -Path $source).Html

# Embed figures so the HTML report can be moved or shared as a single file.
Get-ChildItem -LiteralPath $sourceDirectory -Filter "*.svg" -File | ForEach-Object {
    $reference = 'src="' + $_.Name + '"'
    if ($body.Contains($reference)) {
        $encoded = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($_.FullName))
        $body = $body.Replace($reference, 'src="data:image/svg+xml;base64,' + $encoded + '"')
    }
}
$body = [regex]::Replace($body, '(?s)<table>.*?</table>', '<div class="table-scroll">$0</div>')

$style = @'
:root { color-scheme: light; font-family: Segoe UI, Arial, sans-serif; color: #172033; }
* { box-sizing: border-box; }
body { margin: 0; background: #eef2f7; }
main { max-width: 1440px; margin: 28px auto; padding: 46px 54px; background: white;
       box-shadow: 0 12px 35px rgba(24,40,64,.10); border-radius: 16px; }
h1 { margin: 0 0 20px; font-size: 2rem; line-height: 1.25; }
h2 { margin-top: 46px; padding-top: 22px; border-top: 2px solid #dbe4ef; font-size: 1.55rem; }
h3 { margin-top: 32px; font-size: 1.2rem; }
p, li { line-height: 1.65; }
a { color: #175fba; }
code { background: #f1f5f9; padding: 2px 5px; border-radius: 4px; overflow-wrap: anywhere; }
.table-scroll { overflow-x: auto; margin: 18px 0 27px; border: 1px solid #d7e0eb; border-radius: 10px; }
table { width: 100%; min-width: 740px; border-collapse: collapse; table-layout: fixed; }
th, td { text-align: left; vertical-align: top; padding: 11px 13px; border-bottom: 1px solid #e5ebf3;
         line-height: 1.5; overflow-wrap: anywhere; }
th { font-weight: 700; background: #f1f5f9; position: sticky; top: 0; }
th:first-child, td:first-child { width: 16%; }
th:nth-child(2) { background: #e9f1ff; color: #174b9b; }
th:nth-child(3) { background: #e8f7f1; color: #126347; }
td:nth-child(2) { border-left: 3px solid #b7cefa; }
td:nth-child(3) { border-left: 3px solid #b1e2cf; }
tr:nth-child(even) td { background: #fbfcfe; }
tr:last-child td { border-bottom: 0; }
img { display: block; width: 100%; height: auto; margin: 24px auto; border: 1px solid #e5ebf3;
      border-radius: 10px; background: white; }
@media (max-width: 700px) { body { background: white; } main { margin: 0; padding: 22px 16px;
  box-shadow: none; border-radius: 0; } h1 { font-size: 1.5rem; } }
@media print { body { background: white; } main { margin: 0; padding: 0; max-width: none;
  box-shadow: none; } .table-scroll { overflow: visible; break-inside: avoid; }
  table { min-width: 0; font-size: 9pt; } img { break-inside: avoid; }
  h2, h3 { break-after: avoid; } }
'@

$document = @"
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gemini vs ChatGPT — Metrics 1–3</title>
<style>$style</style>
</head>
<body>
<main>$body</main>
</body>
</html>
"@
[System.IO.File]::WriteAllText($destination, $document, [System.Text.UTF8Encoding]::new($false))
Write-Output $destination
