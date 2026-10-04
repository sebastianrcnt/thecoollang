-- Load with dofile('/path/to/cool.lua').setup({ cmd = { '/path/to/cool', 'lsp' } }).
-- Uses Neovim's built-in LSP client; no third-party plugin is required.
local M = {}

function M.setup(options)
  vim.filetype.add({ extension = { cool = 'cool' } })
  vim.lsp.config('cool', vim.tbl_deep_extend('force', {
    cmd = { 'cool', 'lsp' },
    filetypes = { 'cool' },
    root_markers = { 'cool.mod' },
    workspace_required = false,
    on_attach = function(client, bufnr)
      if client.server_capabilities.completionProvider then
        vim.lsp.completion.enable(true, client.id, bufnr, { autotrigger = true })
      end
    end,
  }, options or {}))
  vim.lsp.enable('cool')
end

return M
