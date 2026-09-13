$ErrorActionPreference = 'SilentlyContinue'

# Où un modèle peut se trouver après un téléchargement Python
$racines = @(
    (Join-Path $env:USERPROFILE '.cache\huggingface'),
    (Join-Path $env:USERPROFILE '.lmstudio\models'),
    (Join-Path $env:USERPROFILE 'Downloads'),
    'D:\',
    'C:\Users\xfive'
)

$vus = @{}

foreach ($r in $racines) {
    if (-not (Test-Path $r)) { continue }
    Get-ChildItem -Path $r -Recurse -Force -Include *.gguf, *.safetensors |
        Where-Object { $_.Length -gt 100MB } |
        ForEach-Object {
            if (-not $vus.ContainsKey($_.FullName)) {
                $vus[$_.FullName] = $true
                $go = [math]::Round($_.Length / 1GB, 2)
                Write-Output ("{0}|{1}" -f $go, $_.FullName)
            }
        }
}

if ($vus.Count -eq 0) { Write-Output 'AUCUN' }
