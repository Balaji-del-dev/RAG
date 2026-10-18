// Render DOT from stdin with the WebAssembly build of Graphviz.
//   node render-dot.mjs [format=svg] [engine=dot] < graph.dot
// npm i @hpcc-js/wasm-graphviz   (or set GRAPHVIZ_WASM to the package's dist/index.js)
const [format = "svg", engine = "dot"] = process.argv.slice(2);
const mod = await import(process.env.GRAPHVIZ_WASM || "@hpcc-js/wasm-graphviz");
const graphviz = await mod.Graphviz.load();
let src = "";
for await (const chunk of process.stdin) src += chunk;
process.stdout.write(graphviz.layout(src, format, engine));
