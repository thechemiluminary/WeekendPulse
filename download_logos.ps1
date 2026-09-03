$slugs = @('afc-bournemouth','arsenal','aston-villa','brentford','brighton-and-hove-albion','chelsea','coventry-city','crystal-palace','everton','fulham','hull-city','ipswich-town','leeds-united','liverpool-fc','manchester-city','manchester-united','newcastle-united','nottingham-forest','sunderland','tottenham-hotspur')
$base_url = 'https://assets.footylogos.com/logos/'
$save_dir = 'C:\Users\hp\Desktop\Claudinho\WeekendPulse\logos\PL'
if (-not (Test-Path $save_dir)) { New-Item -ItemType Directory -Path $save_dir }
foreach ($slug in $slugs) {
    $png_url = "$base_url$slug/$slug-logo-footylogos.png"
    $save_path = Join-Path $save_dir "$slug.png"
    try {
        Invoke-WebRequest -Uri $png_url -OutFile $save_path
        Write-Host "Downloaded: $slug.png"
    } catch {
        Write-Host "Failed: $slug.png"
    }
}