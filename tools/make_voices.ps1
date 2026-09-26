# ヘックス・アリーナのボイスを Windows の読み上げ音声で作る（開発用）
#   powershell -ExecutionPolicy Bypass -File tools\make_voices.ps1
# できたファイルは assets\voice\ に入ります。同じ名前の WAV を置き換えれば、本物の声に差し替えられます。
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait() | Out-Null; $task.Result }

$out = Join-Path $PSScriptRoot "..\assets\voice"
New-Item -ItemType Directory -Force $out | Out-Null
$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$voices = @{}
foreach ($v in [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices) { $voices[$v.DisplayName] = $v }

# ファイル名, 声, 高さ(%), 速さ(%), セリフ
$lines = @(
    @("announce_select",  "Microsoft Ayumi",  "+0%",  "+0%",  "コントローラーを選んでください"),
    @("announce_planning","Microsoft Ayumi",  "+0%",  "+5%",  "準備フェーズ"),
    @("announce_battle",  "Microsoft Ayumi",  "+5%",  "+10%", "戦闘開始！"),
    @("announce_monster", "Microsoft Ayumi",  "+0%",  "+5%",  "モンスター出現！"),
    @("announce_win",     "Microsoft Ayumi",  "+10%", "+5%",  "勝利！"),
    @("announce_lose",    "Microsoft Ayumi",  "-5%",  "-5%",  "敗北…"),
    @("announce_draw",    "Microsoft Ayumi",  "+0%",  "+0%",  "引き分け"),
    @("announce_item",    "Microsoft Ayumi",  "+10%", "+5%",  "アイテムゲット！"),
    @("announce_levelup", "Microsoft Ayumi",  "+10%", "+5%",  "レベルアップ！"),
    @("announce_starup",  "Microsoft Ayumi",  "+10%", "+5%",  "ユニット強化！"),
    @("announce_champion","Microsoft Ayumi",  "+10%", "+0%",  "優勝おめでとう！"),
    @("announce_out",     "Microsoft Ayumi",  "-5%",  "-5%",  "脱落…おつかれさまでした"),
    @("announce_skill",   "Microsoft Ayumi",  "+5%",  "+5%",  "スキル発動！"),
    @("ctrl_midas_pick",  "Microsoft Ichiro", "-10%", "-5%",  "金の匂いがするねぇ。ワシに任せな。"),
    @("ctrl_midas_skill", "Microsoft Ichiro", "-10%", "+0%",  "黄金の取引だ！"),
    @("ctrl_sophia_pick", "Microsoft Ayumi",  "-15%", "-15%", "星が、あなたを導きます。"),
    @("ctrl_sophia_skill","Microsoft Ayumi",  "-15%", "-10%", "星の導きを。"),
    @("ctrl_borg_pick",   "Microsoft Ichiro", "-20%", "+0%",  "任せな、叩き直してやる！"),
    @("ctrl_borg_skill",  "Microsoft Ichiro", "-20%", "+5%",  "渾身の鍛錬！"),
    @("ctrl_lumina_pick", "Microsoft Haruka", "+15%", "+0%",  "契約、しましょ？"),
    @("ctrl_lumina_skill","Microsoft Haruka", "+15%", "+5%",  "来たれ、契約の友よ！"),
    @("ctrl_misty_pick",  "Microsoft Haruka", "-10%", "-15%", "あなたの運命、見えますわ。"),
    @("ctrl_misty_skill", "Microsoft Haruka", "-10%", "-10%", "運命の水晶よ、示しなさい。"),
    @("ctrl_gald_pick",   "Microsoft Ichiro", "-25%", "-10%", "この盾がある限り、倒れはせん。"),
    @("ctrl_gald_skill",  "Microsoft Ichiro", "-25%", "-5%",  "不屈の誓い！"),
    @("ctrl_kai_pick",    "Microsoft Ichiro", "+0%",  "+0%",  "勝利への道筋は、見えている。"),
    @("ctrl_kai_skill",   "Microsoft Ichiro", "+0%",  "+5%",  "奇策の陣、展開！"),
    @("ctrl_arche_pick",  "Microsoft Haruka", "+20%", "+15%", "実験の時間だよっ！"),
    @("ctrl_arche_skill", "Microsoft Haruka", "+20%", "+15%", "禁断の秘薬、ぐいっと！")
)

foreach ($l in $lines) {
    $name, $voice, $pitch, $rate, $text = $l
    if (-not $voices.ContainsKey($voice)) { $voice = "Microsoft Haruka" }
    $synth.Voice = $voices[$voice]
    $ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='ja-JP'><prosody pitch='$pitch' rate='$rate'>$text</prosody></speak>"
    $stream = Await ($synth.SynthesizeSsmlToStreamAsync($ssml)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
    $n = [uint32]$stream.Size
    $null = Await ($reader.LoadAsync($n)) ([uint32])
    $bytes = New-Object byte[] $n
    $reader.ReadBytes($bytes)
    [IO.File]::WriteAllBytes((Join-Path $out "$name.wav"), $bytes)
    Write-Output "wrote $name.wav ($n bytes)"
}
