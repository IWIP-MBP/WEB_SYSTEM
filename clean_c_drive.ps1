param(
    [switch]$Force
)

# Set Output Encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

try {
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "       WSL2 & Docker C Drive Deep Clean Tool" -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This script will perform the following operations:"
    Write-Host "1. Clean Docker builder cache, unused containers, images, and volumes."
    Write-Host "2. Stop Docker service and shut down WSL2 to unlock disk files."
    Write-Host "3. Wait for virtual disk files to release write locks."
    Write-Host "4. Use diskpart to compact all detected virtual disk (.vhdx) files."
    Write-Host "5. Restart Docker services and applications."
    Write-Host ""

    # Scan for target vhdx files (since we are admin, we can scan all users' AppData)
    $vhdxFiles = @()

    # Scan default paths for all user folders in C:\Users
    $userPaths = Get-ChildItem -Path "C:\Users" -Directory -ErrorAction SilentlyContinue
    foreach ($user in $userPaths) {
        $wslPath = Join-Path $user.FullName "AppData\Local\wsl"
        if (Test-Path $wslPath) {
            Get-ChildItem -Path $wslPath -Filter *.vhdx -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
                $vhdxFiles += $_.FullName
            }
        }
        $dockerPath = Join-Path $user.FullName "AppData\Local\Docker\wsl"
        if (Test-Path $dockerPath) {
            Get-ChildItem -Path $dockerPath -Filter *.vhdx -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
                $vhdxFiles += $_.FullName
            }
        }
    }

    # Deduplicate and filter existing files
    $vhdxFiles = $vhdxFiles | Select-Object -Unique | Where-Object { Test-Path $_ }

    if ($vhdxFiles.Count -eq 0) {
        Write-Host "[WARNING] No virtual disk paths (.vhdx) found." -ForegroundColor Yellow
    } else {
        Write-Host "Detected the following virtual disks to compact:" -ForegroundColor Cyan
        $vhdxFiles | ForEach-Object { Write-Host " - $_" -ForegroundColor DarkGray }
    }

    if (-not $Force) {
        $confirm = Read-Host "Are you sure you want to start? [Y/N]"
        if ($confirm -ne "Y" -and $confirm -ne "y") {
            Write-Host "Cleanup cancelled." -ForegroundColor Yellow
            Start-Sleep -Seconds 2
            exit
        }
    }

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "[1/4] Cleaning Docker internal cache..." -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green

    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Write-Host "Running: docker builder prune -a -f"
        docker builder prune -a -f
        Write-Host "Running: docker system prune -f"
        docker system prune -f
        # Commented out to prevent deleting unused volumes that are still needed
        # Write-Host "Running: docker volume prune -f"
        # docker volume prune -f
    } else {
        Write-Host "[WARNING] docker CLI not found, skipping Docker internal prune." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "[2/4] Stopping Docker services and WSL2 VM..." -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green

    Write-Host "Stopping com.docker.service..."
    Stop-Service -Name com.docker.service -ErrorAction SilentlyContinue

    Write-Host "Terminating Docker Desktop processes..."
    Get-Process | Where-Object { $_.Name -like "*docker*" } | Stop-Process -Force -ErrorAction SilentlyContinue

    Write-Host "Shutting down WSL2..."
    wsl --shutdown

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "[3/4] Checking file locks and compacting VHDX..." -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green

    if ($vhdxFiles.Count -eq 0) {
        Write-Host "[WARNING] No virtual disk paths found to compact." -ForegroundColor Yellow
    } else {
        foreach ($vhdxPath in $vhdxFiles) {
            if (-not (Test-Path $vhdxPath)) {
                Write-Host "File not found, skipping: $vhdxPath" -ForegroundColor Yellow
                continue
            }

            Write-Host ""
            Write-Host "Target: $vhdxPath" -ForegroundColor Cyan
            
            # Poll for file release (up to 15 seconds)
            $fileUnlocked = $false
            for ($i = 1; $i -le 5; $i++) {
                try {
                    $fileStream = [System.IO.File]::Open($vhdxPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
                    $fileStream.Close()
                    $fileUnlocked = $true
                    break
                } catch {
                    Write-Host "Waiting for WSL to release disk lock... ($i/5)" -ForegroundColor Yellow
                    Start-Sleep -Seconds 3
                }
            }

            if (-not $fileUnlocked) {
                Write-Host "[WARNING] File is locked. Skipping compaction. Ensure WSL is closed." -ForegroundColor Red
                continue
            }

            # Generate diskpart commands
            $tempFile = [System.IO.Path]::GetTempFileName()
            @"
select vdisk file="$vhdxPath"
attach vdisk readonly
compact vdisk
detach vdisk
"@ | Out-File -FilePath $tempFile -Encoding ascii

            Write-Host "Compacting virtual disk via diskpart..." -ForegroundColor Cyan
            diskpart /s $tempFile
            Remove-Item -Path $tempFile -ErrorAction SilentlyContinue
            Write-Host "Compaction completed successfully!" -ForegroundColor Green
        }
    }

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "[4/4] Restarting Docker services and apps..." -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green

    Write-Host "Starting com.docker.service..."
    Start-Service -Name com.docker.service -ErrorAction SilentlyContinue

    $dockerDesktopPaths = @(
        "C:\Program Files\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe"
    )

    $startedDocker = $false
    foreach ($path in $dockerDesktopPaths) {
        if (Test-Path $path) {
            Write-Host "Launching Docker Desktop..." -ForegroundColor Cyan
            Start-Process -FilePath $path -ErrorAction SilentlyContinue
            $startedDocker = $true
            break
        }
    }

    if (-not $startedDocker) {
        Write-Host "[WARNING] Docker Desktop executable not found, skipping launch." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "* Cleanup and compaction completed successfully!" -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green

} catch {
    Write-Host ""
    Write-Host "[FATAL ERROR] An unexpected error occurred during execution:" -ForegroundColor Red
    Write-Host $_.Exception.ToString() -ForegroundColor Red
} finally {
    if (-not $Force) {
        Read-Host "Press Enter to exit..."
    }
}
