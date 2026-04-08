<#
.SYNOPSIS
    MakerTools full release pipeline — use this instead of the Forge release card.

.DESCRIPTION
    Handles every step in one shot so releases never partially fail:
      1. Clears stale GH_TOKEN (the cause of repeated 401 failures)
      2. Verifies gh CLI is authenticated before touching anything
      3. Commits staged changes, pushes the feature branch, merges to main
      4. Re-creates the version tag cleanly
      5. Creates the GitHub release
      6. Zips PathMaker, TextureForge, and MisterWizard
      7. Uploads the zip assets to the release
      8. Cleans up temp files and returns to the feature branch

.PARAMETER Version
    Release version tag in the form vX.Y.Z  (e.g. v1.0.17)

.EXAMPLE
    .\release.ps1 v1.0.17
#>
param(
    [Parameter(Mandatory, HelpMessage = "Version tag — e.g. v1.0.17")]
    [ValidatePattern('^v\d+\.\d+\.\d+$')]
    [string]$Version
)

Set-StrictMode -Version Latest

# ── Step 1: Kill the stale GH_TOKEN that Forge Terminal injects into every PTY ──
# fterm.exe spawns pwsh with -NoProfile so profiles never run; the token lives
# in fterm's own process env and is inherited by every child shell.  Removing it
# here forces gh to fall back to keyring auth, which is always valid.
Remove-Item Env:\GH_TOKEN -ErrorAction SilentlyContinue

# ── Step 2: Verify gh is authenticated before doing any git work ─────────────
Write-Host "`n[1/6] Checking gh auth..." -ForegroundColor Cyan
$authOutput = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host $authOutput -ForegroundColor Red
    Write-Error "gh CLI is not authenticated. Run:  gh auth login"
    exit 1
}
Write-Host "      ✅  Authenticated." -ForegroundColor Green

# ── Step 3: Git — commit, push feature branch, fast-forward merge to main ────
Write-Host "`n[2/6] Publishing branch and merging to main..." -ForegroundColor Cyan

$featureBranch = git branch --show-current
git add -A
git commit -m "Release $Version" --allow-empty
if ($LASTEXITCODE -ne 0) { Write-Error "git commit failed"; exit 1 }

git push origin $featureBranch
if ($LASTEXITCODE -ne 0) { Write-Error "git push feature branch failed"; exit 1 }

git checkout main
git pull origin main

git merge $featureBranch --no-edit
if ($LASTEXITCODE -ne 0) { Write-Error "git merge failed — resolve conflicts first"; exit 1 }

git push origin main
if ($LASTEXITCODE -ne 0) { Write-Error "git push main failed"; exit 1 }

# Re-create the tag cleanly (delete remote + local first so re-runs are safe)
git push origin ":refs/tags/$Version" 2>$null
git tag -d $Version 2>$null
git tag $Version
git push origin $Version
if ($LASTEXITCODE -ne 0) { Write-Error "git push tag failed"; exit 1 }

Write-Host "      ✅  Tag $Version pushed." -ForegroundColor Green

# ── Step 4: Create the GitHub release ────────────────────────────────────────
Write-Host "`n[3/6] Creating GitHub release..." -ForegroundColor Cyan
gh release delete $Version --yes 2>$null

gh release create $Version `
    --title "Release $Version" `
    --notes  "Release $Version" `
    --latest
if ($LASTEXITCODE -ne 0) { Write-Error "gh release create failed"; exit 1 }

Write-Host "      ✅  Release created." -ForegroundColor Green

# ── Step 5: Build zip assets ──────────────────────────────────────────────────
Write-Host "`n[4/6] Building zip assets..." -ForegroundColor Cyan

$repoRoot   = $PSScriptRoot
$stagingDir = Join-Path $env:TEMP "MakerTools-release-$Version"
Remove-Item $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item    $stagingDir -ItemType Directory | Out-Null

$zipPaths = @()
foreach ($toolName in @("PathMaker", "TextureForge", "MisterWizard")) {
    $toolSource = Join-Path $repoRoot $toolName
    $zipDest    = Join-Path $stagingDir "$toolName-$Version.zip"

    if (-not (Test-Path $toolSource)) {
        Write-Warning "Skipping $toolName — folder not found at $toolSource"
        continue
    }

    Compress-Archive -Path $toolSource -DestinationPath $zipDest -CompressionLevel Optimal
    $sizeKb = [math]::Round((Get-Item $zipDest).Length / 1KB, 1)
    Write-Host "      $toolName-$Version.zip  ($sizeKb KB)" -ForegroundColor Green
    $zipPaths += $zipDest
}

# ── Step 6: Upload assets ─────────────────────────────────────────────────────
Write-Host "`n[5/6] Uploading assets to GitHub..." -ForegroundColor Cyan
gh release upload $Version @zipPaths --clobber
if ($LASTEXITCODE -ne 0) { Write-Error "gh release upload failed"; exit 1 }

Write-Host "      ✅  $(($zipPaths).Count) assets uploaded." -ForegroundColor Green

# ── Step 7: Clean up and return to feature branch ────────────────────────────
Write-Host "`n[6/6] Cleaning up..." -ForegroundColor Cyan
Remove-Item $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
git checkout $featureBranch

Write-Host "`n🚀  Release $Version is live:" -ForegroundColor Green
Write-Host "    https://github.com/mikejsmith1985/MakerTools/releases/tag/$Version`n" -ForegroundColor Cyan
