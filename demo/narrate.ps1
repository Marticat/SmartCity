param([switch]$SynthesizeOnly)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
Add-Type -AssemblyName System.Speech
$spec = [System.IO.File]::ReadAllText((Join-Path $PSScriptRoot "narration.json"), [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$target = Join-Path (Get-Location) "artifacts/narration"
[System.IO.Directory]::CreateDirectory($target) | Out-Null
$speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $speaker.SelectVoice($spec.voice)
    $speaker.Rate = 1
    $format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
        [System.Speech.AudioFormat.EncodingFormat]::Pcm, 22050, 16, 1, 44100, 2, $null)
    for ($i = 0; $i -lt $spec.segments.Count; $i++) {
        $speaker.SetOutputToWaveFile((Join-Path $target "$i.wav"), $format)
        $speaker.Speak([string]$spec.segments[$i])
        $speaker.SetOutputToNull()
    }
} finally {
    $speaker.Dispose()
}
if ($SynthesizeOnly) { Write-Output "Synthesized $($spec.segments.Count) local voice segments"; exit 0 }
& ".venv/Scripts/python.exe" -m scripts.build_narrated_demo
if ($LASTEXITCODE -ne 0) { throw "Narrated demo build failed" }
