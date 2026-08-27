param(
    [int]$Orders = 250000,
    [int]$InventoryDays = 365,
    [switch]$LoadPostgres
)

$ErrorActionPreference = "Stop"
$arguments = @(
    "-m", "src.pipeline",
    "--orders", $Orders,
    "--inventory-days", $InventoryDays
)

if ($LoadPostgres) {
    $arguments += "--load-postgres"
}

python @arguments

