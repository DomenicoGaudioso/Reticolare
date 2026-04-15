<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8"/>
  <title>Travi reticolari 2D — Guida</title>
  <style>
    body { font-family: system-ui, Arial; max-width: 920px; margin: 2rem auto; line-height: 1.6; }
    code { background:#f3f3f3; padding:.15rem .35rem; border-radius:6px; }
    h1,h2 { margin-top: 1.6rem; }
  </style>
</head>
<body>
  <h1>Web app trave reticolare 2D (parametrica) — Guida rapida</h1>

  <h2>1) Genera il modello</h2>
  <p>In sidebar scegli: tipologia (Warren/Howe/Pratt/Nielsen/...), lunghezza <code>L</code>, altezza <code>H</code>,
     numero pannelli, aree e modulo elastico.</p>

  <h2>2) Modifica le tabelle</h2>
  <p>Puoi modificare direttamente <code>nodes</code>, <code>elements</code>, <code>restraints</code>, <code>node_loads</code>.</p>

  <h2>3) Solve</h2>
  <p>Premi <b>Solve ▸ Linear Static</b> per ottenere spostamenti e sforzi assiali.</p>

  <h2>4) Download</h2>
  <p>Scarica l’XLSX con i fogli risultati: <code>results_nodal</code> e <code>results_elements</code>.</p>

  <h2>Semplice appoggio</h2>
  <p>Di default: nodo inferiore sinistro incernierato (ux=1, uy=1) e nodo inferiore destro carrello (ux=0, uy=1).
     Puoi sempre modificare i vincoli nel foglio <code>restraints</code>.</p>
</body>
</html>
