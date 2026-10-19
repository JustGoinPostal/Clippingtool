(() => {
  const busy = new Set();
  const originalLabels = new WeakMap();

  const style = document.createElement('style');
  style.textContent = `
    button.renderBusy{opacity:.68;cursor:wait!important;pointer-events:none}
    .renderSpinner{display:inline-block;width:12px;height:12px;margin-right:6px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;vertical-align:-2px;animation:postalSpin .7s linear infinite}
    .renderBusyNote{margin-top:8px;padding:8px 10px;border:1px solid #826d36;border-radius:9px;color:#efd08e;background:#1a160d;font-size:12px;font-weight:800}
    @keyframes postalSpin{to{transform:rotate(360deg)}}
  `;
  document.head.appendChild(style);

  function renderButtonsForClip(id) {
    const needle1 = `renderVariant(${Number(id)},`;
    const needle2 = `renderAll(${Number(id)})`;
    return [...document.querySelectorAll('#clips button')].filter(btn => {
      const code = btn.getAttribute('onclick') || '';
      return code.includes(needle1) || code.includes(needle2);
    });
  }

  function editorRenderButtons() {
    return [...document.querySelectorAll('#modal button')].filter(btn => {
      const code = btn.getAttribute('onclick') || '';
      return code.startsWith('renderEditor(') || code.startsWith('renderEditorAll(');
    });
  }

  function setButtonBusy(btn, on, text='Rendering…') {
    if (!btn) return;
    if (on) {
      if (!originalLabels.has(btn)) originalLabels.set(btn, btn.innerHTML);
      btn.disabled = true;
      btn.classList.add('renderBusy');
      btn.innerHTML = `<span class="renderSpinner"></span>${text}`;
    } else {
      btn.disabled = false;
      btn.classList.remove('renderBusy');
      if (originalLabels.has(btn)) {
        btn.innerHTML = originalLabels.get(btn);
        originalLabels.delete(btn);
      }
    }
  }

  function setClipBusy(id, on, clicked=null, label='Rendering…') {
    const buttons = renderButtonsForClip(id);
    for (const btn of buttons) {
      if (!originalLabels.has(btn)) originalLabels.set(btn, btn.innerHTML);
      btn.disabled = on;
      btn.classList.toggle('renderBusy', on);
      if (!on && originalLabels.has(btn)) {
        btn.innerHTML = originalLabels.get(btn);
        originalLabels.delete(btn);
      }
    }
    if (clicked && on) setButtonBusy(clicked, true, label);

    const editId = typeof editing !== 'undefined' && editing ? Number(editing.id) : 0;
    if (editId === Number(id)) {
      for (const btn of editorRenderButtons()) {
        if (!originalLabels.has(btn)) originalLabels.set(btn, btn.innerHTML);
        btn.disabled = on;
        btn.classList.toggle('renderBusy', on);
        if (!on && originalLabels.has(btn)) {
          btn.innerHTML = originalLabels.get(btn);
          originalLabels.delete(btn);
        }
      }
      const results = document.querySelector('#renderResults');
      if (results && on) {
        results.innerHTML = `<div class="renderBusyNote"><span class="renderSpinner"></span>${label} Please keep AutoClip open. The render buttons are locked until it finishes.</div>`;
      }
    }

    const anchor = buttons[0]?.closest('.clip');
    if (anchor) {
      let note = anchor.querySelector('.renderBusyNote');
      if (on) {
        if (!note) {
          note = document.createElement('div');
          note.className = 'renderBusyNote';
          anchor.appendChild(note);
        }
        note.innerHTML = `<span class="renderSpinner"></span>${label} Render controls are locked until this clip finishes.`;
      } else if (note) {
        note.remove();
      }
    }
  }

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  async function waitForRender(id) {
    try {
      while (true) {
        await sleep(650);
        const clip = await j(`/api/clips/${Number(id)}`);
        if (String(clip.status || '') !== 'rendering') {
          if (String(clip.status || '') === 'error') {
            throw new Error('Render failed. Check the AutoClip window/debug output for the FFmpeg error.');
          }
          break;
        }
      }
      await refresh();
      if (typeof editing !== 'undefined' && editing && Number(editing.id) === Number(id)) {
        await refreshEditor();
      }
    } finally {
      busy.delete(Number(id));
      setClipBusy(id, false);
    }
  }

  async function startRender(id, variant=null, all=false) {
    id = Number(id);
    if (busy.has(id)) return;
    busy.add(id);
    const clicked = (window.event && window.event.currentTarget instanceof HTMLElement) ? window.event.currentTarget : null;
    const label = all ? 'Rendering all sizes…' : `Rendering ${variant || ''}…`;
    setClipBusy(id, true, clicked, label);
    try {
      if (all) {
        await j(`/api/clips/${id}/render-all`, {method:'POST'});
      } else {
        await j(`/api/clips/${id}/render`, {
          method:'POST',
          headers:{'content-type':'application/json'},
          body:JSON.stringify({variant})
        });
      }
      await waitForRender(id);
    } catch (e) {
      busy.delete(id);
      setClipBusy(id, false);
      alert(e);
    }
  }

  window.renderVariant = async function(id, variant) {
    return startRender(id, variant, false);
  };

  window.renderAll = async function(id) {
    return startRender(id, null, true);
  };

  window.renderEditor = async function(variant) {
    if (typeof editing === 'undefined' || !editing) return;
    await saveEdit();
    return startRender(editing.id, variant, false);
  };

  window.renderEditorAll = async function() {
    if (typeof editing === 'undefined' || !editing) return;
    await saveEdit();
    return startRender(editing.id, null, true);
  };

  // Recover the loading UI after a page refresh while a render thread is still active.
  setInterval(() => {
    if (typeof lastClips === 'undefined') return;
    for (const clip of (lastClips || [])) {
      const id = Number(clip.id);
      if (String(clip.status || '') === 'rendering' && !busy.has(id)) {
        busy.add(id);
        setClipBusy(id, true, null, 'Rendering…');
        waitForRender(id).catch(e => alert(e));
      }
    }
  }, 900);
})();
