# v1.1.5.21 \u5b89\u5168\u8865\u4e01: \u7528 PowerShell \u5728\u6bcf\u4e2a commit \u4e0a\u626b\u63cf \u5e76\u6e05\u9664 API key
# \u7528\u6cd5: git filter-branch -f --tree-filter "powershell -ExecutionPolicy Bypass -File release/.git_filter_secrets.ps1" -- --all

Get-ChildItem -Path . -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '*.yaml' -or $_.Name -like '*.json' -or $_.Name -like '*.yml' -or $_.Name -like '*.env' } |
    ForEach-Object {
        $p = $_.FullName
        $raw = Get-Content -LiteralPath $p -Raw -ErrorAction SilentlyContinue
        if ($null -eq $raw) { return }
        $new = $raw `
            -replace 'sk-5e6\.\.\.b223', 'sk-CLEARED' `
            -replace 'sk-c3D\.\.\.TKoE', 'sk-CLEARED' `
            -replace 'sk-5e6[a-zA-Z0-9]{30,}', 'sk-CLEARED' `
            -replace 'sk-c3D[a-zA-Z0-9]{30,}', 'sk-CLEARED' `
            -replace '(?<=api_key:?\s*[\x27\x22]?)sk-[a-zA-Z0-9_\-]{16,}(?=[\x27\x22\s]?)', 'sk-CLEARED'
        if ($new -ne $raw) {
            Set-Content -LiteralPath $p -Value $new -NoNewline -Encoding UTF8
            Write-Host "  scrubbed: $p"
        }
    }
