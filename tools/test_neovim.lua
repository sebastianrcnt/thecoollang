-- Integration through Neovim's actual document sync, UTF conversion, diagnostic
-- store, request client and edit application; no hand-written JSON-RPC transport.
local function wait_for(description, predicate)
  assert(vim.wait(20000, predicate, 20), 'timeout: ' .. description)
end
local function run()
  local source = vim.env.COOL_EDITOR_SOURCE
  local library = vim.env.COOL_EDITOR_LIBRARY
  local publish = {}
  local exit_code, exit_signal
  dofile(vim.env.COOL_EDITOR_CONFIG).setup({
    cmd = { vim.env.COOL_EDITOR_CLI, 'lsp' },
    flags = { debounce_text_changes = 0 },
    handlers = {
      ['textDocument/publishDiagnostics'] = function(err, result, ctx, config)
        publish[result.uri] = (publish[result.uri] or 0) + 1
        vim.lsp.handlers['textDocument/publishDiagnostics'](err, result, ctx, config)
      end,
    },
    on_exit = function(code, signal) exit_code, exit_signal = code, signal end,
  })
  vim.cmd('filetype on')
  vim.cmd.edit(vim.fn.fnameescape(source))
  local buffer = vim.api.nvim_get_current_buf()
  assert(vim.bo[buffer].filetype == 'cool', 'filetype registration failed')
  local client
  wait_for('client initialization', function()
    client = vim.lsp.get_clients({ bufnr = buffer, name = 'cool' })[1]
    return client and client.initialized
  end)
  assert(client.offset_encoding == 'utf-16', client.offset_encoding)
  assert(client.root_dir == vim.fs.dirname(source), tostring(client.root_dir))
  assert(client.server_capabilities.definitionProvider)
  assert(client.server_capabilities.completionProvider)
  local uri = vim.uri_from_bufnr(buffer)
  wait_for('initial diagnostic', function() return #vim.diagnostic.get(buffer) == 1 end)
  local initial = vim.diagnostic.get(buffer)[1]
  local line = vim.api.nvim_buf_get_lines(buffer,2,3,false)[1]
  assert(initial.lnum == 2 and initial.col == line:find('missing',1,true)-1, vim.inspect(initial))
  assert(initial.message:find('unknown variable',1,true), initial.message)
  assert(vim.bo[buffer].fileformat == 'dos', 'CRLF fixture did not load as DOS')
  local function replace(buf, lines)
    local target_uri = vim.uri_from_bufnr(buf)
    local previous = publish[target_uri] or 0
    vim.api.nvim_buf_set_lines(buf,0,-1,false,lines)
    wait_for('didChange diagnostics', function() return (publish[target_uri] or 0) > previous end)
  end
  local valid = { 'package main;', 'import l "example.test/editor/lib";',
    'fn main(){let emoji="🙂";let value=l.answer();assert(value==7);}' }
  replace(buffer,valid)
  assert(#vim.diagnostic.get(buffer)==0, vim.inspect(vim.diagnostic.get(buffer)))
  local function request(method, row, byte_col)
    vim.api.nvim_set_current_buf(buffer)
    vim.api.nvim_win_set_cursor(0,{row,byte_col})
    local params = vim.lsp.util.make_position_params(0,client.offset_encoding)
    local response,err = client:request_sync(method,params,20000,buffer)
    assert(response and not response.err, vim.inspect(response or err))
    return response.result
  end
  local definition = request('textDocument/definition',3,valid[3]:find('answer',1,true)-1)
  assert(#definition==1 and vim.uri_to_fname(definition[1].uri)==library, vim.inspect(definition))
  assert(definition[1].range.start.character == 19, vim.inspect(definition))
  -- Let the client derive the UTF-16 position after an emoji; apply the server's
  -- replacement through Neovim's native edit adapter and re-check the buffer.
  local partial = vim.deepcopy(valid)
  partial[3] = partial[3]:gsub('l.answer','l.ans')
  replace(buffer,partial)
  assert(#vim.diagnostic.get(buffer)>0)
  local completion = request('textDocument/completion',3,partial[3]:find('ans',1,true)+2)
  local item
  for _,candidate in ipairs(completion.items) do if candidate.label=='answer' then item=candidate end end
  assert(item, vim.inspect(completion))
  local before_edit = publish[uri]
  vim.lsp.util.apply_text_edits({item.textEdit},buffer,client.offset_encoding)
  wait_for('applied completion diagnostics',function() return publish[uri]>before_edit end)
  assert(vim.api.nvim_buf_get_lines(buffer,2,3,false)[1]==valid[3])
  assert(#vim.diagnostic.get(buffer)==0)
  -- A second unsaved buffer must participate in the first buffer's package.
  vim.cmd.edit(vim.fn.fnameescape(library))
  local library_buffer = vim.api.nvim_get_current_buf()
  wait_for('library attach',function() return #vim.lsp.get_clients({bufnr=library_buffer,name='cool'})==1 end)
  assert(vim.lsp.get_clients({bufnr=library_buffer,name='cool'})[1].id==client.id,'package buffers did not reuse the client')
  wait_for('library initial publication',function() return (publish[vim.uri_from_bufnr(library_buffer)] or 0)>0 end)
  replace(library_buffer,{'package lib;pub fn answer()->i64{return absent;}'})
  assert(#vim.diagnostic.get(library_buffer)==1)
  -- A broken unrelated dependency body must not disable main's completion.
  completion = request('textDocument/completion',3,valid[3]:find('answer',1,true)+2)
  assert(completion.items[1] and completion.items[1].label=='answer',vim.inspect(completion))
  local lib_uri = vim.uri_from_bufnr(library_buffer)
  local prior = publish[uri] or 0
  vim.api.nvim_buf_delete(library_buffer,{force=true})
  wait_for('didClose returns to disk',function() return (publish[uri] or 0)>prior end)
  assert(#vim.diagnostic.get(buffer)==0)
  assert((publish[lib_uri] or 0)>0)
  -- New module files need declaration candidates before they have a package header.
  local new_path=vim.fs.dirname(source)..'/new.cool'
  vim.cmd.edit(vim.fn.fnameescape(new_path))
  local new_buffer=vim.api.nvim_get_current_buf()
  local new_uri=vim.uri_from_bufnr(new_buffer)
  wait_for('new empty file attach',function() return #vim.lsp.get_clients({bufnr=new_buffer,name='cool'})==1 end)
  wait_for('new empty file diagnostics',function() return (publish[new_uri] or 0)>0 end)
  assert(#vim.diagnostic.get(buffer)>0, 'normal package validation was suppressed')
  local new_response,new_error=client:request_sync('textDocument/completion',
    vim.lsp.util.make_position_params(0,client.offset_encoding),20000,new_buffer)
  assert(new_response and not new_response.err,vim.inspect(new_response or new_error))
  local declarations={}
  for _,candidate in ipairs(new_response.result.items) do declarations[candidate.label]=true end
  assert(declarations.fn and declarations.package and declarations.struct,vim.inspect(new_response))
  prior=publish[uri] or 0
  vim.api.nvim_buf_delete(new_buffer,{force=true})
  wait_for('new file close/reset',function() return (publish[uri] or 0)>prior end)
  assert(#vim.diagnostic.get(buffer)==0)
  assert(vim.uv.fs_stat(new_path)==nil,'empty buffer was written to disk')
  client:stop(false)
  wait_for('graceful shutdown',function() return exit_code~=nil end)
  assert(exit_code==0 and exit_signal==0,vim.inspect({exit_code,exit_signal}))
  -- Standalone files outside a module must attach without an invented root.
  exit_code, exit_signal = nil, nil
  vim.cmd.edit(vim.fn.fnameescape(vim.env.COOL_EDITOR_STANDALONE))
  local standalone = vim.api.nvim_get_current_buf()
  local standalone_uri = vim.uri_from_bufnr(standalone)
  wait_for('standalone client',function()
    client=vim.lsp.get_clients({bufnr=standalone,name='cool'})[1]
    return client and client.initialized
  end)
  assert(client.root_dir==nil,tostring(client.root_dir))
  wait_for('standalone diagnostics',function() return (publish[standalone_uri] or 0)>0 end)
  assert(#vim.diagnostic.get(standalone)==0)
  local standalone_line=vim.api.nvim_buf_get_lines(standalone,0,1,false)[1]
  vim.api.nvim_win_set_cursor(0,{1,standalone_line:find('assert(value',1,true)+8})
  local params=vim.lsp.util.make_position_params(0,client.offset_encoding)
  local response,err=client:request_sync('textDocument/completion',params,20000,standalone)
  assert(response and not response.err,vim.inspect(response or err))
  assert(response.result.items[1] and response.result.items[1].label=='value',vim.inspect(response))
  client:stop(false)
  wait_for('standalone shutdown',function() return exit_code~=nil end)
  assert(exit_code==0 and exit_signal==0)
  return {version=vim.version(),encoding=client.offset_encoding,diagnostics=true,
    definition=true,completion_edit=true,unsaved_dependency=true,close_reset=true,empty_module_file=true,standalone=true,shutdown_code=exit_code}
end
local ok,result = xpcall(run,debug.traceback)
if ok then
  vim.fn.writefile({vim.json.encode(result)},vim.env.COOL_EDITOR_REPORT)
  vim.cmd('qa!')
else
  io.stderr:write(tostring(result)..'\n')
  vim.cmd('cquit 1')
end
