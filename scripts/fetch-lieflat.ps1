$ErrorActionPreference = 'Stop'
$PinnedCommit = 'eace082a317b696c5570c25826a53a7fa113e984'
$Target = Join-Path $PSScriptRoot '..\third_party\lieflat-charts'
$Target = [System.IO.Path]::GetFullPath($Target)

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
git -c "safe.directory=$($ProjectRoot.Replace('\','/'))" -C $ProjectRoot submodule update --init --recursive
$Commit = git -c "safe.directory=$($Target.Replace('\','/'))" -C $Target rev-parse HEAD
if ($Commit -ne $PinnedCommit) {
    throw "Unexpected Lieflat Charts commit: $Commit (expected $PinnedCommit)"
}
Write-Output "Lieflat Charts is pinned at $Commit"
