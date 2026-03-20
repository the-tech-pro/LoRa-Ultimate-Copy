param(
  [string]$Port = "COM5",
  [int]$Baud = 115200
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$idNames = [System.Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
$idNames['s'] = 'speed'
$idNames['m'] = 'motor_rpm'
$idNames['i'] = 'current'
$idNames['v'] = 'voltage_total'
$idNames['w'] = 'voltage_lower'
$idNames['t'] = 'throttle_in'
$idNames['d'] = 'throttle_out'
$idNames['T'] = 'throttle_v'
$idNames['a'] = 'temp1'
$idNames['b'] = 'temp2'
$idNames['c'] = 'temp3'
$idNames['L'] = 'launch'
$idNames['C'] = 'cycle_view'
$idNames['r'] = 'gear_ratio'
$idNames['B'] = 'brake'
$idNames['V'] = 'ref_v'

$displayOrder = @('s','m','i','v','w','t','d','T','a','b','c','r','L','C','B','V')

function Decode-EchookValue {
  param(
    [byte]$Data1,
    [byte]$Data2
  )

  $raw1 = [int]$Data1
  $raw2 = [int]$Data2
  $d1 = if ($raw1 -eq 0xFF) { 0 } else { $raw1 }
  $d2 = if ($raw2 -eq 0xFF) { 0 } else { $raw2 }

  if ($raw1 -ge 128 -and $raw1 -ne 0xFF) {
    $hundreds = $raw1 - 128
    return [pscustomobject]@{
      Value = ($hundreds * 100) + $d2
      Mode = 'int'
    }
  }

  return [pscustomobject]@{
    Value = $d1 + ($d2 / 100.0)
    Mode = 'float'
  }
}

function Get-PrintableByte {
  param([int]$Byte)

  if ($Byte -ge 32 -and $Byte -le 126) {
    return [string][char]$Byte
  }

  return "."
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "eChook UART Viewer"
$form.StartPosition = "CenterScreen"
$form.AutoSize = $true
$form.AutoSizeMode = "GrowAndShrink"
$form.Font = New-Object System.Drawing.Font("Consolas", 10)

$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.AutoSize = $true
$titleLabel.Font = New-Object System.Drawing.Font("Consolas", 11, [System.Drawing.FontStyle]::Bold)
$titleLabel.Text = "eChook UART Viewer"

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.AutoSize = $true
$statusLabel.Text = "Disconnected"
$statusLabel.ForeColor = [System.Drawing.Color]::DarkRed

$portLabel = New-Object System.Windows.Forms.Label
$portLabel.AutoSize = $true
$portLabel.Text = "Port:"

$portCombo = New-Object System.Windows.Forms.ComboBox
$portCombo.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
$portCombo.Width = 120

$refreshButton = New-Object System.Windows.Forms.Button
$refreshButton.Text = "Refresh"
$refreshButton.AutoSize = $true

$baudLabel = New-Object System.Windows.Forms.Label
$baudLabel.AutoSize = $true
$baudLabel.Text = ("Baud: {0}" -f $Baud)

$connectButton = New-Object System.Windows.Forms.Button
$connectButton.Text = "Connect"
$connectButton.AutoSize = $true

$rawButton = New-Object System.Windows.Forms.Button
$rawButton.Text = "Show Raw Data"
$rawButton.AutoSize = $true

$headerPanel = New-Object System.Windows.Forms.TableLayoutPanel
$headerPanel.AutoSize = $true
$headerPanel.AutoSizeMode = "GrowAndShrink"
$headerPanel.ColumnCount = 4
$headerPanel.RowCount = 2
$headerPanel.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
$headerPanel.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
$headerPanel.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
$headerPanel.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
$headerPanel.Controls.Add($titleLabel, 0, 0)
$headerPanel.SetColumnSpan($titleLabel, 4)
$headerPanel.Controls.Add($statusLabel, 0, 1)
$headerPanel.Controls.Add($portLabel, 1, 1)
$headerPanel.Controls.Add($portCombo, 2, 1)
$headerPanel.Controls.Add($refreshButton, 3, 1)

$table = New-Object System.Windows.Forms.TableLayoutPanel
$table.AutoSize = $true
$table.AutoSizeMode = "GrowAndShrink"
$table.ColumnCount = 2
$table.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 65)))
$table.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 35)))

$valueLabels = @{}

foreach ($idKey in $displayOrder) {
  $name = 'unknown'
  if ($idNames.TryGetValue($idKey, [ref]$name)) {
  }

  $labelName = New-Object System.Windows.Forms.Label
  $labelName.AutoSize = $true
  $labelName.Text = ("{0} ({1})" -f $name, $idKey)

  $labelValue = New-Object System.Windows.Forms.Label
  $labelValue.AutoSize = $true
  $labelValue.Text = "--"

  $row = $table.RowCount
  $table.RowCount = $row + 1
  $table.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
  $table.Controls.Add($labelName, 0, $row)
  $table.Controls.Add($labelValue, 1, $row)

  $valueLabels[$idKey] = $labelValue
}

$controlsPanel = New-Object System.Windows.Forms.FlowLayoutPanel
$controlsPanel.AutoSize = $true
$controlsPanel.WrapContents = $false
$controlsPanel.Controls.Add($baudLabel)
$controlsPanel.Controls.Add($connectButton)
$controlsPanel.Controls.Add($rawButton)

$main = New-Object System.Windows.Forms.TableLayoutPanel
$main.Dock = "Fill"
$main.AutoSize = $true
$main.AutoSizeMode = "GrowAndShrink"
$main.Padding = New-Object System.Windows.Forms.Padding(10)
$main.ColumnCount = 1
$main.RowCount = 3
$main.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
$main.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
$main.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
$main.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
$main.Controls.Add($headerPanel, 0, 0)
$main.Controls.Add($controlsPanel, 0, 1)
$main.Controls.Add($table, 0, 2)

$form.Controls.Add($main)

$rawForm = New-Object System.Windows.Forms.Form
$rawForm.Text = "eChook Raw UART"
$rawForm.StartPosition = "CenterParent"
$rawForm.Size = New-Object System.Drawing.Size(760, 480)
$rawForm.Font = New-Object System.Drawing.Font("Consolas", 10)

$rawTextBox = New-Object System.Windows.Forms.TextBox
$rawTextBox.Multiline = $true
$rawTextBox.ReadOnly = $true
$rawTextBox.ScrollBars = [System.Windows.Forms.ScrollBars]::Vertical
$rawTextBox.WordWrap = $false
$rawTextBox.Dock = "Fill"
$rawTextBox.Font = New-Object System.Drawing.Font("Consolas", 10)

$clearRawButton = New-Object System.Windows.Forms.Button
$clearRawButton.Text = "Clear"
$clearRawButton.AutoSize = $true

$rawHeaderLabel = New-Object System.Windows.Forms.Label
$rawHeaderLabel.AutoSize = $true
$rawHeaderLabel.Text = "Timestamp    Hex   ASCII"

$rawHeaderPanel = New-Object System.Windows.Forms.FlowLayoutPanel
$rawHeaderPanel.AutoSize = $true
$rawHeaderPanel.WrapContents = $false
$rawHeaderPanel.Dock = "Fill"
$rawHeaderPanel.Controls.Add($rawHeaderLabel)
$rawHeaderPanel.Controls.Add($clearRawButton)

$rawMain = New-Object System.Windows.Forms.TableLayoutPanel
$rawMain.Dock = "Fill"
$rawMain.Padding = New-Object System.Windows.Forms.Padding(10)
$rawMain.ColumnCount = 1
$rawMain.RowCount = 2
$rawMain.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
$rawMain.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
$rawMain.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100)))
$rawMain.Controls.Add($rawHeaderPanel, 0, 0)
$rawMain.Controls.Add($rawTextBox, 0, 1)

$rawForm.Controls.Add($rawMain)

$script:buffer = New-Object System.Collections.Generic.List[byte]
$script:valueLabels = $valueLabels
$script:statusLabel = $statusLabel
$script:connectButton = $connectButton
$script:portCombo = $portCombo
$script:rawForm = $rawForm
$script:rawTextBox = $rawTextBox
$script:rawLoggingEnabled = $true
$script:sp = $null
$script:isOpen = $false
$script:currentPort = $null
$script:lastFrameUtc = $null
$script:lastKnownUtc = $null
$script:lastNonZeroUtc = $null
$script:recentIds = @{}
$script:maxRawLogChars = 60000
$dataWindowSeconds = 2
$minDistinctIds = 3

function Set-Status {
  param(
    [string]$Text,
    [string]$State
  )
  if ($script:statusLabel -and -not $script:statusLabel.IsDisposed) {
    $script:statusLabel.Text = $Text
    switch ($State) {
      "connected" { $script:statusLabel.ForeColor = [System.Drawing.Color]::DarkGreen }
      "warning" { $script:statusLabel.ForeColor = [System.Drawing.Color]::DarkOrange }
      default { $script:statusLabel.ForeColor = [System.Drawing.Color]::DarkRed }
    }
  }
}

function Set-ButtonState {
  param([bool]$IsOpen)
  if ($script:connectButton -and -not $script:connectButton.IsDisposed) {
    $script:connectButton.Text = if ($IsOpen) { "Disconnect" } else { "Connect" }
  }
}

function Add-RawLogLine {
  param([string]$Text)

  if (-not $script:rawLoggingEnabled) {
    return
  }

  if (-not $script:rawTextBox -or $script:rawTextBox.IsDisposed) {
    return
  }

  try {
    $script:rawTextBox.AppendText($Text + [Environment]::NewLine)
    if ($script:rawTextBox.TextLength -gt $script:maxRawLogChars) {
      $script:rawTextBox.Text = $script:rawTextBox.Text.Substring($script:rawTextBox.TextLength - 40000)
      $script:rawTextBox.SelectionStart = $script:rawTextBox.TextLength
    }
    $script:rawTextBox.ScrollToCaret()
  } catch {
    # Raw logging is optional; never let UI logging break serial capture.
    $script:rawLoggingEnabled = $false
  }
}

function Close-SerialPort {
  if ($script:sp) {
    try {
      if ($script:sp.IsOpen) { $script:sp.Close() }
    } catch {
    }
    try {
      $script:sp.Dispose()
    } catch {
    }
    $script:sp = $null
  }
  $script:isOpen = $false
  $script:currentPort = $null
}

function Open-SerialPort {
  param([string]$SelectedPort)
  Close-SerialPort
  try {
    $sp = New-Object System.IO.Ports.SerialPort $SelectedPort,$Baud,'None',8,'One'
    $sp.ReadTimeout = 0
    $sp.Open()
    $script:sp = $sp
    $script:isOpen = $true
    $script:currentPort = $SelectedPort
    $script:lastFrameUtc = $null
    $script:lastKnownUtc = $null
    $script:lastNonZeroUtc = $null
    $script:recentIds.Clear()
    $script:rawLoggingEnabled = $true
    Set-ButtonState $true
    Set-Status ("Port open: waiting for data on {0} @ {1}" -f $SelectedPort, $Baud) "warning"
  } catch {
    Set-Status ("Disconnected: {0}" -f $_.Exception.Message) "disconnected"
    Set-ButtonState $false
    return
  }
  Add-RawLogLine ("=== Logging raw UART bytes on {0} @ {1} ===" -f $SelectedPort, $Baud)
}

function Update-Status {
  if (-not $script:isOpen -or -not $script:sp -or -not $script:sp.IsOpen) {
    Set-Status "Disconnected" "disconnected"
    Set-ButtonState $false
    return
  }

  $now = [DateTime]::UtcNow
  $recentIdCount = 0
  foreach ($key in @($script:recentIds.Keys)) {
    $seen = $script:recentIds[$key]
    if (($now - $seen).TotalSeconds -le $dataWindowSeconds) {
      $recentIdCount++
    }
  }

  $recentFrame = $script:lastFrameUtc -and ($now - $script:lastFrameUtc).TotalSeconds -le $dataWindowSeconds
  $recentKnown = $script:lastKnownUtc -and ($now - $script:lastKnownUtc).TotalSeconds -le $dataWindowSeconds
  $recentNonZero = $script:lastNonZeroUtc -and ($now - $script:lastNonZeroUtc).TotalSeconds -le $dataWindowSeconds

  if ($recentKnown -and ($recentIdCount -ge $minDistinctIds -or $recentNonZero)) {
    Set-Status ("Connected: eChook data OK on {0}" -f $script:currentPort) "connected"
  } elseif ($recentFrame -or $recentKnown) {
    Set-Status ("Port open: frames seen, validating data on {0}" -f $script:currentPort) "warning"
  } else {
    Set-Status ("Port open: waiting for eChook data on {0}" -f $script:currentPort) "warning"
  }
  Set-ButtonState $true
}

$refreshButton.Add_Click({
  $ports = [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
  $portCombo.Items.Clear()
  foreach ($p in $ports) { [void]$portCombo.Items.Add($p) }
  if ($ports.Count -gt 0) {
    $portCombo.SelectedItem = $ports[0]
  } else {
    Set-Status "Disconnected: no COM ports found" "disconnected"
  }
})

$connectButton.Add_Click({
  if ($script:isOpen) {
    Close-SerialPort
    Set-Status "Disconnected" "disconnected"
    Set-ButtonState $false
    return
  }
  $selected = $portCombo.SelectedItem
  if (-not $selected) {
    Set-Status "Disconnected: select a COM port" "disconnected"
    Set-ButtonState $false
    return
  }
  Open-SerialPort -SelectedPort $selected
})

$rawButton.Add_Click({
  if (-not $script:rawForm.Visible) {
    $script:rawForm.Show()
  }
  $script:rawForm.BringToFront()
  $script:rawForm.Focus()
})

$clearRawButton.Add_Click({
  if ($script:rawTextBox -and -not $script:rawTextBox.IsDisposed) {
    $script:rawTextBox.Clear()
  }
})

$rawForm.Add_FormClosing({
  param($sender, $e)

  if ($e.CloseReason -eq [System.Windows.Forms.CloseReason]::UserClosing) {
    $e.Cancel = $true
    $sender.Hide()
  }
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 50
$timer.Add_Tick({
  if (-not $script:sp -or -not $script:sp.IsOpen) { return }
  try {
    while ($script:sp.BytesToRead -gt 0) {
      $b = $script:sp.ReadByte()
      if ($b -lt 0) { break }
      $byteTime = [DateTime]::Now
      Add-RawLogLine ("{0:HH:mm:ss.fff}  0x{1:X2}   {2}" -f $byteTime, $b, (Get-PrintableByte -Byte $b))
      $script:buffer.Add([byte]$b)
      if ($script:buffer.Count -gt 5) { $script:buffer.RemoveAt(0) }

      if ($script:buffer.Count -eq 5 -and $script:buffer[0] -eq 123 -and $script:buffer[4] -eq 125) {
        $id = [char]$script:buffer[1]
        $decoded = Decode-EchookValue -Data1 $script:buffer[2] -Data2 $script:buffer[3]
        $idKey = [string]$id
        $valueText = if ($decoded.Mode -eq 'float') { "{0:0.00}" -f $decoded.Value } else { "{0:0}" -f $decoded.Value }
        $now = [DateTime]::UtcNow
        $script:lastFrameUtc = $now

        if ($script:valueLabels.ContainsKey($idKey)) {
          $script:valueLabels[$idKey].Text = $valueText
          $script:lastKnownUtc = $now
          $script:recentIds[$idKey] = $now
          if ($decoded.Value -ne 0) {
            $script:lastNonZeroUtc = $now
          }
        }
        $script:buffer.Clear()
      }
    }
  } catch {
    Set-Status ("Disconnected: {0}" -f $_.Exception.Message) "disconnected"
    Close-SerialPort
  }
  Update-Status
})

$form.Add_Shown({
  $ports = [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
  foreach ($p in $ports) { [void]$portCombo.Items.Add($p) }
  if ($ports -contains $Port) {
    $portCombo.SelectedItem = $Port
  } elseif ($ports.Count -gt 0) {
    $portCombo.SelectedItem = $ports[0]
  }
  if ($portCombo.SelectedItem) {
    Open-SerialPort -SelectedPort $portCombo.SelectedItem
  } else {
    Set-Status "Disconnected: no COM ports found" "disconnected"
  }
  $timer.Start()
})

$form.Add_FormClosing({
  $timer.Stop()
  Close-SerialPort
  if ($script:rawForm -and -not $script:rawForm.IsDisposed) {
    $script:rawForm.Dispose()
  }
})

[void]$form.ShowDialog()
