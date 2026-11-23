# Bring in this computer (SPOKE-3 "Courier", hbar 2026-11-16). The one line from your brain's home,
# pasted into PowerShell (Start menu, type PowerShell):
#
#   $env:BRAIN_TOKEN="imp_..."; irm https://<your brain>/api/bf/laptop/agent.ps1 | iex
#
# What it does, once, then it is gone:
#  1. It looks through your user folder and your cloud folders (OneDrive, Google Drive, Dropbox,
#     iCloud Drive, Box), and the session history of Codex and Claude Code (.codex\sessions,
#     .claude\projects: only the session files, nothing else in those folders): names, sizes and
#     dates only. Nothing is read yet.
#  2. It sends that LIST to your own brain over HTTPS, with the one-time key from the line.
#     Never listed, only counted: hidden files, keys, passwords, mail, browser data, system folders.
#  3. You choose on your brain's home what to bring. It then sends exactly those files, and only
#     files it listed itself, then closes the key.
#  4. It stops. Nothing is installed or saved, nothing keeps running, and your brain has no way into
#     this computer: this program only ever calls out to your brain.
#
# It runs as you, needs no administrator, no SSH server, no VPN and no download to open: PowerShell
# 5.1 as Windows ships it. The never-send rules below come from scripts/import/brain_import.py on the
# brain (one source). Read it before you run it: open the address above in a browser.
# Docs: docs/IMPORT.md, "Bring in this computer" (brainfoundry-nous).

& {
$ErrorActionPreference = 'Stop'
$AgentVersion = 'agent-ps1/0.1.0'
$W = @{
@@WORDS@@
}
function Say([string]$k) { Write-Host ($W[$k] -f $args) }

$SkipDirs = @(@@SKIP_DIRS@@)
$DirSuffixes = @(@@DIR_SUFFIXES@@)
$SkipFiles = @(@@SKIP_FILES@@)
$Readable = ' @@READABLE@@ '
$Audio = ' @@AUDIO@@ '
$Images = ' @@IMAGES@@ '
$MaxFile = [int64]@@MAX_FILE@@
$MaxAudio = [int64]@@MAX_AUDIO@@
$MaxEntries = @@MAX_ENTRIES@@
$MaxName = 400
# the coding agents' history: label, folder under the user folder, deepest file (path parts, 0 any)
$HistoryRoots = @(@@HISTORY@@)
$HistoryExt = '@@HISTORY_EXT@@'

$token = $env:BRAIN_TOKEN
if (-not $token) { $token = Read-Host $W.ASKTOKEN }
$token = "$token".Trim()
$base = if ($env:BRAIN_BASE) { $env:BRAIN_BASE } else { '@@BASE@@' }
$base = $base.TrimEnd('/')
$homeDir = if ($env:BRAIN_AGENT_HOME) { $env:BRAIN_AGENT_HOME } else { [Environment]::GetFolderPath('UserProfile') }
$poll = if ($env:BRAIN_AGENT_POLL) { [double]$env:BRAIN_AGENT_POLL } else { 3 }
Remove-Item Env:BRAIN_TOKEN -ErrorAction SilentlyContinue

if ($token -notmatch '^imp_[A-Za-z0-9_-]{32,64}$') { Say BADTOKEN; return }
if ($base -notmatch '^https://' -and $base -notmatch '^http://(127\.0\.0\.1|localhost)(:\d+)?$') { Say BADBASE; return }

# TLS 1.2 on older Windows PowerShell (the default there can be TLS 1.0)
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
Add-Type -AssemblyName System.Net.Http
$client = New-Object System.Net.Http.HttpClient
$client.Timeout = [TimeSpan]::FromMinutes(15)
$client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $token)
$client.DefaultRequestHeaders.UserAgent.ParseAdd($AgentVersion)
$finished = $false

function Call([string]$method, [string]$path, $content) {
    $req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($method), ($base + $path))
    if ($content) { $req.Content = $content }
    try {
        $res = $client.SendAsync($req).GetAwaiter().GetResult()
        $body = $res.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        return @{ code = [int]$res.StatusCode; body = $body }
    } catch {
        return @{ code = 0; body = $_.Exception.Message }
    }
}
function Detail($r) {
    try { return ($r.body | ConvertFrom-Json).detail } catch { return ("" + $r.body).Substring(0, [Math]::Min(200, ("" + $r.body).Length)) }
}
function Human([double]$n) {
    $u = 'B', 'KB', 'MB', 'GB', 'TB'; $i = 0
    while ($n -ge 1024 -and $i -lt 4) { $n /= 1024; $i++ }
    if ($i -eq 0) { return "{0:N0} {1}" -f $n, $u[$i] } else { return "{0:N1} {1}" -f $n, $u[$i] }
}
function Ext([string]$name) { $i = $name.LastIndexOf('.'); if ($i -lt 0) { return '' } else { return $name.Substring($i + 1).ToLowerInvariant() } }
function SkipDir([string]$name) {
    if ($name.StartsWith('.')) { return $true }
    $low = $name.ToLowerInvariant()
    if ($SkipDirs -contains $low) { return $true }
    foreach ($s in $DirSuffixes) { if ($low.EndsWith($s)) { return $true } }
    return $false
}
function Why([string]$base_, [string]$name, [int64]$size) {
    if ($base_.StartsWith('.')) { return 'hidden' }
    $low = $base_.ToLowerInvariant()
    foreach ($p in $SkipFiles) { if ($low -like $p) { return 'secret' } }
    $e = Ext $base_
    $isAudio = $e -and $Audio.Contains(" $e ")
    if (-not $e -or (-not $Readable.Contains(" $e ") -and -not $isAudio)) { return 'not readable by Knowledge' }
    if ($isAudio -and $size -gt $MaxAudio) { return 'over 200 MB' }
    if (-not $isAudio -and $size -gt $MaxFile) { return 'over 25 MB' }
    if ($size -eq 0) { return 'empty' }
    if ($name.Length -gt $MaxName -or $name -match '[\x00-\x1f]') { return 'name too long or odd' }
    return ''
}
function HistWhy([string]$base_, [string]$rel, [string]$name, [int64]$size, [int]$depth) {
    if ($base_.StartsWith('.')) { return 'hidden' }
    $low = $base_.ToLowerInvariant()
    foreach ($p in $SkipFiles) { if ($low -like $p) { return 'secret' } }
    if ((Ext $base_) -ne $HistoryExt -or ($depth -gt 0 -and $rel.Split('/').Count -gt $depth)) { return 'not a chat' }
    if ($size -gt $MaxFile) { return 'over 25 MB' }
    if ($size -eq 0) { return 'empty' }
    if ($name.Length -gt $MaxName -or $name -match '[\x00-\x1f]') { return 'name too long or odd' }
    return ''
}
function IsLink($info) {
    try { $lt = $info.LinkType } catch { $lt = $null }
    return ($lt -eq 'SymbolicLink' -or $lt -eq 'Junction')
}
function JStr([string]$s) {
    $sb = New-Object System.Text.StringBuilder ($s.Length + 2)
    [void]$sb.Append('"')
    foreach ($c in $s.ToCharArray()) {
        $n = [int]$c
        if ($c -eq '"') { [void]$sb.Append('\"') }
        elseif ($c -eq '\') { [void]$sb.Append('\\') }
        elseif ($n -lt 32 -or $n -gt 126) { [void]$sb.Append(('\u{0:x4}' -f $n)) }
        else { [void]$sb.Append($c) }
    }
    [void]$sb.Append('"')
    return $sb.ToString()
}

try {
    # ── 1. the key ──
    $r = Call 'GET' '/documents/import-laptop/check' $null
    if ($r.code -ne 200) { Say REFUSED $r.code (Detail $r); $finished = $true; return }
    if (-not (($r.body | ConvertFrom-Json).survey)) { Say NOTSURVEY; $finished = $true; return }
    Say CONNECTED

    # ── 2. where to look: the user folder, then the cloud folders it has ──
    $roots = New-Object System.Collections.ArrayList
    function AddRoot([string]$label, [string]$path) {
        if (-not (Test-Path -LiteralPath $path -PathType Container)) { return }
        foreach ($x in $roots) { if ($x.path -eq $path) { return } }
        $n = @($roots | Where-Object { $_.label -eq $label -or $_.label -like "$label (*" }).Count
        if ($n -gt 0) { $label = "$label ($($n + 1))" }
        [void]$roots.Add(@{ label = $label; path = $path })
    }
    foreach ($d in @(Get-ChildItem -LiteralPath $homeDir -Directory -Force -ErrorAction SilentlyContinue)) {
        if (IsLink $d) { continue }
        $low = $d.Name.ToLowerInvariant()
        if ($low -eq 'icloud drive' -or $low -eq 'iclouddrive') { AddRoot 'iCloud Drive' $d.FullName }
        elseif ($low -eq 'google drive' -or $low -eq 'my drive') { AddRoot 'Google Drive' $d.FullName }
        elseif ($low -eq 'dropbox' -or $low.StartsWith('dropbox (')) { AddRoot 'Dropbox' $d.FullName }
        elseif ($low -eq 'onedrive' -or $low.StartsWith('onedrive - ')) { AddRoot 'OneDrive' $d.FullName }
        elseif ($low -eq 'box') { AddRoot 'Box' $d.FullName }
    }
    foreach ($letter in 'DEFGHIJKLMNOPQRSTUVWXYZ'.ToCharArray()) {
        $gd = "$($letter):\My Drive"
        try { if ([IO.Directory]::Exists($gd)) { AddRoot 'Google Drive' $gd } } catch {}
    }
    $cloudPaths = @{}
    foreach ($x in $roots) { $cloudPaths[$x.path.ToLowerInvariant()] = $true }
    # the coding agents' history: only these two folders under .codex and .claude, never the rest
    # (auth.json, config, credentials); no link or junction followed
    $hist = New-Object System.Collections.ArrayList
    foreach ($h in $HistoryRoots) {
        $top = Join-Path $homeDir ($h.sub.Split('\')[0])
        $dir = Join-Path $homeDir $h.sub
        $ok = $true
        foreach ($p in @($top, $dir)) {
            $gi = Get-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
            if (-not $gi -or -not $gi.PSIsContainer -or (IsLink $gi)) { $ok = $false; break }
        }
        if ($ok) { [void]$hist.Add(@{ label = $h.label; path = $dir; depth = [int]$h.depth }) }
    }

    # ── 3. the walk ──
    Say LOOKING
    $rows = New-Object System.Text.StringBuilder
    $places = @{}
    $sizes = @{}
    $skipped = @{}
    $private = New-Object System.Collections.Generic.SortedSet[string]
    $st = @{ count = 0; total = [int64]0 }
    function Walk([string]$label, [string]$root, [int]$histDepth = -1) {
        $stack = New-Object System.Collections.Stack
        $stack.Push($root)
        while ($stack.Count -gt 0) {
            $dir = [string]$stack.Pop()
            $info = New-Object System.IO.DirectoryInfo $dir
            try {
                $subs = @($info.EnumerateDirectories())
                $files = @($info.EnumerateFiles())
            } catch {
                $rel = $dir.Substring([Math]::Min($dir.Length, $root.Length)).TrimStart('\', '/')
                $top = if ($rel) { $rel.Split('\/'.ToCharArray())[0] } else { Split-Path -Leaf $dir }
                [void]$private.Add($(if ($label) { "$label/$top" } else { $top }))
                continue
            }
            foreach ($s in $subs) {
                if (SkipDir $s.Name) { continue }
                if (IsLink $s) { continue }
                if (-not $label -and $cloudPaths.ContainsKey($s.FullName.ToLowerInvariant())) { continue }
                $stack.Push($s.FullName)
            }
            foreach ($f in $files) {
                if (IsLink $f) { continue }
                $rel = $f.FullName.Substring($root.Length).TrimStart('\', '/').Replace('\', '/')
                $top = if ($rel.Contains('/')) { $rel.Substring(0, $rel.IndexOf('/')) } else { '(home)' }
                $key = if ($label) { "$label/$top" } else { $top }
                $name = if ($label) { "$label/$rel" } else { $rel }
                $why = if ($histDepth -ge 0) { HistWhy $f.Name $rel $name $f.Length $histDepth } else { Why $f.Name $name $f.Length }
                if (-not $why -and $st.count -ge $MaxEntries) { $why = 'over the list limit' }
                if ($why) { $k = "$($key): $why"; $skipped[$k] = 1 + [int]$skipped[$k]; continue }
                $mtime = [DateTimeOffset]::new($f.LastWriteTimeUtc).ToUnixTimeSeconds()
                if ($st.count -gt 0) { [void]$rows.Append(',') }
                [void]$rows.Append('[').Append((JStr $name)).Append(',').Append($f.Length).Append(',').Append($mtime).Append(']')
                $places[$name] = $f.FullName
                $sizes[$name] = $f.Length
                $st.count++
                $st.total += $f.Length
            }
        }
    }
    Walk '' $homeDir
    foreach ($x in $roots) { Say ROOT $x.label; Walk $x.label $x.path }
    foreach ($x in $hist) { Say ROOT $x.label; Walk $x.label $x.path $x.depth }

    Say FOUND $st.count (Human $st.total)
    if ($roots.Count) { Say CLOUDS (($roots | ForEach-Object { $_.label }) -join ', ') } else { Say NOCLOUDS }
    if ($hist.Count) { Say HISTORY (($hist | ForEach-Object { $_.label }) -join ', ') }
    $nSkip = 0; foreach ($v in $skipped.Values) { $nSkip += $v }
    if ($nSkip -gt 0) { Say NEVER $nSkip }
    if ($private.Count) { Say PRIVATE (@($private) -join ', ') }

    # ── 4. the list goes to the brain (gzip JSON; names, sizes, dates; no content) ──
    $sk = New-Object System.Text.StringBuilder
    foreach ($k in $skipped.Keys) { if ($sk.Length) { [void]$sk.Append(',') }; [void]$sk.Append((JStr $k)).Append(':').Append($skipped[$k]) }
    foreach ($p in $private) { if ($sk.Length) { [void]$sk.Append(',') }; [void]$sk.Append((JStr "$($p): kept private by the system")).Append(':0') }
    $rl = (@($roots) + @($hist) | ForEach-Object { JStr $_.label }) -join ','
    $json = '{"version":"' + $AgentVersion + '","os":"windows","files":[' + $rows.ToString() + '],"skipped":{' + $sk.ToString() + '},"roots":[' + $rl + ']}'
    $raw = (New-Object System.Text.UTF8Encoding $false).GetBytes($json)
    $ms = New-Object System.IO.MemoryStream
    $gz = New-Object System.IO.Compression.GZipStream $ms, ([System.IO.Compression.CompressionMode]::Compress)
    $gz.Write($raw, 0, $raw.Length); $gz.Close()
    $body = [System.Net.Http.ByteArrayContent]::new($ms.ToArray())
    $body.Headers.ContentType = New-Object System.Net.Http.Headers.MediaTypeHeaderValue 'application/json'
    $body.Headers.ContentEncoding.Add('gzip')
    $r = Call 'POST' '/documents/import-laptop/check' $body
    if ($r.code -ne 200) { Say REFUSED $r.code (Detail $r); return }
    $j = $r.body | ConvertFrom-Json
    Write-Host ''
    Say LISTSENT $j.files $j.groups
    Say CHOOSE

    # ── 5. wait for the choice on the home ──
    while ($true) {
        Start-Sleep -Milliseconds ([int]($poll * 1000))
        $r = Call 'GET' '/documents/import-laptop/check?form=lines' $null
        if ($r.code -eq 401) { Say EXPIRED; $finished = $true; return }
        if ($r.code -ne 200) { continue }
        $lines = $r.body -split "`n"
        if ($lines[0].Trim() -eq 'state chosen') { break }
    }

    # ── 6. bring exactly what was chosen, and only names this run listed itself ──
    $send = New-Object System.Collections.ArrayList
    $miss = 0; $sendTotal = [int64]0
    foreach ($ln in ($lines | Select-Object -Skip 1)) {
        if (-not $ln) { continue }
        $kind, $name = $ln.TrimEnd("`r").Split([char[]]"`t", 2)
        if ($places.ContainsKey($name)) { [void]$send.Add(@($kind, $name)); $sendTotal += $sizes[$name] } else { $miss++ }
    }
    Write-Host ''
    Say CHOSE $send.Count (Human $sendTotal)
    if ($miss) { Say IGNORED $miss }
    $i = 0; $sent = 0; $refused = 0
    foreach ($item in $send) {
        $i++
        $kind = $item[0]; $name = $item[1]; $path = $places[$name]
        $keep = ''
        if ($kind -eq 'files' -and $Images.Contains(" $(Ext $name) ")) { $keep = 'file' }
        $fi = New-Object System.IO.FileInfo $path
        if (-not $fi.Exists -or (IsLink $fi)) {
            $r = @{ code = 404; body = '{"detail":"not on this computer any more"}' }
        } else {
            $stream = $null
            try {
                $stream = [IO.File]::OpenRead($path)
                $form = New-Object System.Net.Http.MultipartFormDataContent
                $form.Add((New-Object System.Net.Http.StringContent $name), 'path')
                $form.Add((New-Object System.Net.Http.StringContent $keep), 'keep')
                $fc = New-Object System.Net.Http.StreamContent $stream
                $fc.Headers.ContentType = New-Object System.Net.Http.Headers.MediaTypeHeaderValue 'application/octet-stream'
                $form.Add($fc, 'file', $fi.Name)
                $r = Call 'POST' '/documents/import-laptop/file' $form
            } catch {
                $r = @{ code = 0; body = $_.Exception.Message }
            } finally {
                if ($stream) { $stream.Dispose() }
            }
        }
        if ($r.code -eq 200) {
            $sent++
            $mark = if ($r.body -match '"where"') { $W.KEPT } else { $W.OK }
        } else {
            $refused++
            $mark = $W.REFUSEDONE -f "$($r.code) $(Detail $r)"
        }
        Write-Host ("[{0}/{1}] {2}  {3}" -f $i, $send.Count, $name, $mark)
        if ($r.code -eq 401) { Say STOPPED; break }
    }
    [void](Call 'POST' '/documents/import-laptop/finish' $null)
    $finished = $true
    Write-Host ''
    Say DONE $sent $refused
} finally {
    if (-not $finished) {
        [void](Call 'POST' '/documents/import-laptop/finish' $null)
        Say ABORTED
    }
    $client.Dispose()
    $token = $null
}
}
