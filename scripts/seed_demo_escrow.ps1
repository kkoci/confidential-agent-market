# Seed a deposit on ConfidentialEscrow and trigger a green-path settle.
#
# Usage:
#   .\seed_demo_escrow.ps1 -base 'https://<your-phala-cvm-url>'
#
# Runs the full demo cycle:
#   1. POST /market/bid + /market/ask     -> fresh UUIDs in CVM memory
#   2. cast keccak  "$bid_id:$ask_id"     -> 32-byte escrowId (same as escrow.py)
#   3. KXUSD.approve(escrow, AMOUNT)      -> from service wallet
#   4. escrow.deposit(escrowId, seller, AMOUNT)
#   5. POST /market/settle                -> CVM negotiates, attests via TDX,
#                                            calls settle() -> contract releases
#                                            KXUSD to seller
#   6. Reads receipt; expects status=1
#
# Requires .env with AGENT_PRIVATE_KEY.
# Foundry binaries at ~/.foundry/bin (forge/cast).

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $base,
    [string] $rpc     = 'https://rpc-testnet.gokite.ai/',
    [string] $kxusd   = '0x1b7425d288ea676FCBc65c29711fccF0B6D5c293',
    [string] $escrow  = '0xBB2835fC4d189340a98084A50DD0B36b4Ff50Ca2',
    [string] $wallet  = '0x4812fC05e79ddc616346d10A8826B2bdf5e6ab20',
    [string] $amount  = '1000000000000000000'
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13

$cast = "$env:USERPROFILE\.foundry\bin\cast.exe"
if (-not (Test-Path $cast)) { throw "cast.exe not found at $cast - install Foundry first." }

$envPath = Join-Path (Split-Path -Parent $PSScriptRoot) '.env'
$content = Get-Content $envPath -Raw
if ($content -notmatch 'AGENT_PRIVATE_KEY=([0-9a-fA-Fx]+)') { throw "AGENT_PRIVATE_KEY not found in $envPath" }
$pk = $matches[1]

Write-Host ''
Write-Host '=== 1. Posting bid + ask to CVM ==='
$bid = Invoke-RestMethod -Uri "$base/market/bid" -Method Post -ContentType 'application/json' -Body (@{ asset='WKITE'; price='1.00'; quantity='10'; side='buy'  } | ConvertTo-Json)
$ask = Invoke-RestMethod -Uri "$base/market/ask" -Method Post -ContentType 'application/json' -Body (@{ asset='WKITE'; price='0.95'; quantity='10'; side='sell' } | ConvertTo-Json)
Write-Host "bid_id = $($bid.order_id)"
Write-Host "ask_id = $($ask.order_id)"

Write-Host ''
Write-Host '=== 2. Deriving escrowId (keccak256 of bid_id:ask_id) ==='
$preimage  = "$($bid.order_id):$($ask.order_id)"
$escrowId  = (& $cast keccak $preimage).Trim()
Write-Host "preimage  = $preimage"
Write-Host "escrowId  = $escrowId"

Write-Host ''
Write-Host '=== 3. KXUSD approve to escrow ==='
$tx1 = & $cast send $kxusd 'approve(address,uint256)' $escrow $amount --rpc-url $rpc --private-key $pk --json | ConvertFrom-Json
$tx1Status = [string]$tx1.status
Write-Host "approve tx     : $($tx1.transactionHash)"
Write-Host "approve status : $tx1Status  (0x1 = success)"
if ($tx1Status -ne '0x1' -and $tx1Status -ne '1') { throw 'approve reverted' }

Write-Host ''
Write-Host '=== 4. escrow.deposit(escrowId, seller, amount) ==='
$tx2 = & $cast send $escrow 'deposit(bytes32,address,uint256)' $escrowId $wallet $amount --rpc-url $rpc --private-key $pk --json | ConvertFrom-Json
$tx2Status = [string]$tx2.status
Write-Host "deposit tx     : $($tx2.transactionHash)"
Write-Host "deposit status : $tx2Status  (0x1 = success)"
if ($tx2Status -ne '0x1' -and $tx2Status -ne '1') { throw 'deposit reverted' }

Write-Host ''
Write-Host '=== 5. Verifying escrow state on-chain ==='
$state = & $cast call $escrow 'getEscrow(bytes32)((address,address,uint256,bool,bool))' $escrowId --rpc-url $rpc
Write-Host "escrow state: $state"

Write-Host ''
Write-Host '=== 6. POST /market/settle ==='
$settleBody = @{ bid_id=$bid.order_id; ask_id=$ask.order_id; buyer_address=$wallet; seller_address=$wallet } | ConvertTo-Json
$settle = Invoke-RestMethod -Uri "$base/market/settle" -Method Post -ContentType 'application/json' -TimeoutSec 240 -Body $settleBody
Write-Host "status       : $($settle.status)"
Write-Host "rounds       : $($settle.rounds)"
Write-Host "agreed_price : $($settle.agreed_price)"
Write-Host "tx_hash      : $($settle.tx_hash)"
$att = [string]$settle.attestation
$attLabel = if ($att.Length -gt 200) { ' (real TDX)' } else { " ($att)" }
Write-Host "attestation  : $($att.Length) chars$attLabel"

if ($settle.tx_hash) {
    Write-Host ''
    Write-Host '=== 7. On-chain settle receipt ==='
    $hash = if ($settle.tx_hash.StartsWith('0x')) { $settle.tx_hash } else { "0x$($settle.tx_hash)" }
    $rcpt = & $cast receipt $hash --rpc-url $rpc 2>&1
    $rcpt | Select-String -Pattern '^(status|blockNumber|gasUsed|to|transactionHash)' | ForEach-Object { Write-Host $_.Line }
}

Write-Host ''
Write-Host '=== Done ==='
