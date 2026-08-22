$src = 'D:\Documents\Default Project\Nilou\anime_nilou_08476697\Mesh\Face.obj'
$out = 'D:\Documents\Default Project\Nilou\mod_shrink_test\head\Face.obj'

function Get-VertStats($p) {
    $vs = New-Object System.Collections.Generic.List[double[]]
    foreach ($line in Get-Content $p) {
        if ($line -like 'v *') {
            $t = $line -split ' '
            $vs.Add(@([double]$t[1], [double]$t[2], [double]$t[3]))
        }
    }
    $n = $vs.Count
    $xs = @(); $ys = @(); $zs = @()
    foreach ($v in $vs) { $xs += $v[0]; $ys += $v[1]; $zs += $v[2] }
    [pscustomobject]@{
        count = $n
        xMin = ($xs | Measure-Object -Minimum).Minimum
        xMax = ($xs | Measure-Object -Maximum).Maximum
        yMin = ($ys | Measure-Object -Minimum).Minimum
        yMax = ($ys | Measure-Object -Maximum).Maximum
        zMin = ($zs | Measure-Object -Minimum).Minimum
        zMax = ($zs | Measure-Object -Maximum).Maximum
    }
}

$s = Get-VertStats $src
$o = Get-VertStats $out
Write-Host "=== Face.obj compare ==="
Write-Host ("vtx source    : {0}" -f $s.count)
Write-Host ("vtx exported  : {0}" -f $o.count)
Write-Host ("Y range src   : {0:F6}  ..  {1:F6}  (Δ={2:F6})" -f $s.yMin, $s.yMax, ($s.yMax - $s.yMin))
Write-Host ("Y range out   : {0:F6}  ..  {1:F6}  (Δ={2:F6})" -f $o.yMin, $o.yMax, ($o.yMax - $o.yMin))
$ratio = ($o.yMax - $o.yMin) / ($s.yMax - $s.yMin)
Write-Host ("Y-scale ratio : {0:F4}  (target 0.65)" -f $ratio)

if ([Math]::Abs($ratio - 0.65) -lt 0.02) {
    Write-Host "`n[OK] Y scaled near 0.65 as expected"
} else {
    Write-Host "`n[WARN] Y ratio $ratio is far from 0.65"
}
