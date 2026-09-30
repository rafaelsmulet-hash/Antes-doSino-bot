/**
 * Simulador de estruturas com opcoes - Antes do Sino
 * =====================================================
 * Pagina 100% client-side, sem dependencia de dado externo - o
 * usuario informa preco do ativo, strikes e premios (dados dele, nao
 * nossos: nao ha fonte gratuita de cadeia de opcoes da B3 em tempo
 * real hoje, ver CLAUDE.md regra 5 - nunca inventamos isso). As
 * formulas de payoff sao matematica padrao de mercado (nao
 * proprietaria), calculadas numericamente sobre uma faixa de precos
 * do ativo no vencimento - ferramenta educacional, nunca recomendacao
 * de investimento (CLAUDE.md regra 4).
 */
(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Motor de payoff - funcoes puras, sem DOM, pra poder testar isolado
  // (ver /scratchpad, script de teste ad hoc rodado com node).
  // ---------------------------------------------------------------------

  function payoffTravaAlta(S, params) {
    // Compra call K1 (paga premioCompra) + vende call K2>K1 (recebe premioVenda)
    var ganhoOpcoes = Math.max(S - params.k1, 0) - Math.max(S - params.k2, 0);
    return ganhoOpcoes - (params.premioCompra - params.premioVenda);
  }

  function payoffTravaBaixa(S, params) {
    // Compra put K1 (paga premioCompra) + vende put K2<K1 (recebe premioVenda)
    var ganhoOpcoes = Math.max(params.k1 - S, 0) - Math.max(params.k2 - S, 0);
    return ganhoOpcoes - (params.premioCompra - params.premioVenda);
  }

  function payoffCollar(S, params) {
    // Possui o ativo (S0) + compra put kPut (paga premioPut) + vende call kCall (recebe premioCall)
    var resultadoAtivo = S - params.s0;
    var protecaoPut = Math.max(params.kPut - S, 0) - params.premioPut;
    var tetoCall = -Math.max(S - params.kCall, 0) + params.premioCall;
    return resultadoAtivo + protecaoPut + tetoCall;
  }

  function payoffPutProtetora(S, params) {
    // Possui o ativo (S0) + compra put k (paga premio)
    var resultadoAtivo = S - params.s0;
    var protecao = Math.max(params.k - S, 0) - params.premio;
    return resultadoAtivo + protecao;
  }

  var ESTRUTURAS = {
    trava_alta: {
      label: "Trava de Alta (Bull Call Spread)",
      descricao: "Compra 1 call no strike menor e vende 1 call no strike maior - reduz o custo da aposta em alta, mas limita o lucro maximo.",
      campoPrecoAtual: "precoAtual",
      campos: [
        { id: "precoAtual", label: "Preço atual do ativo (só pra marcar no gráfico)", min0: true },
        { id: "k1", label: "Strike da call comprada (K1)", min0: true },
        { id: "k2", label: "Strike da call vendida (K2, maior que K1)", min0: true },
        { id: "premioCompra", label: "Prêmio pago na call comprada" },
        { id: "premioVenda", label: "Prêmio recebido na call vendida" },
      ],
      payoff: payoffTravaAlta,
    },
    trava_baixa: {
      label: "Trava de Baixa (Bear Put Spread)",
      descricao: "Compra 1 put no strike maior e vende 1 put no strike menor - reduz o custo da aposta em baixa, mas limita o lucro maximo.",
      campoPrecoAtual: "precoAtual",
      campos: [
        { id: "precoAtual", label: "Preço atual do ativo (só pra marcar no gráfico)", min0: true },
        { id: "k1", label: "Strike da put comprada (K1)", min0: true },
        { id: "k2", label: "Strike da put vendida (K2, menor que K1)", min0: true },
        { id: "premioCompra", label: "Prêmio pago na put comprada" },
        { id: "premioVenda", label: "Prêmio recebido na put vendida" },
      ],
      payoff: payoffTravaBaixa,
    },
    collar: {
      label: "Collar (Trava Protetora)",
      descricao: "Você já possui o ativo, compra uma put pra travar uma perda mínima e vende uma call pra financiar o custo - limita perda E ganho.",
      campoPrecoAtual: "s0",
      campos: [
        { id: "s0", label: "Preço atual do ativo (S0)", min0: true },
        { id: "kPut", label: "Strike da put comprada (proteção, abaixo de S0)", min0: true },
        { id: "premioPut", label: "Prêmio pago na put" },
        { id: "kCall", label: "Strike da call vendida (teto, acima de S0)", min0: true },
        { id: "premioCall", label: "Prêmio recebido na call" },
      ],
      payoff: payoffCollar,
    },
    put_protetora: {
      label: "Put Protetora (Protective Put)",
      descricao: "Você já possui o ativo e compra uma put pra travar uma perda mínima - o ganho na alta continua sem limite, pelo custo do prêmio.",
      campoPrecoAtual: "s0",
      campos: [
        { id: "s0", label: "Preço atual do ativo (S0)", min0: true },
        { id: "k", label: "Strike da put comprada" },
        { id: "premio", label: "Prêmio pago na put" },
      ],
      payoff: payoffPutProtetora,
    },
  };

  // Resolve o preco atual/de referencia de um conjunto de parametros,
  // qualquer que seja a estrutura (ver campoPrecoAtual acima) - usado
  // tanto pra centralizar a faixa simulada quanto pro marcador
  // "Preço atual" no grafico.
  function precoAtualDeParams(estruturaKey, params) {
    var campo = ESTRUTURAS[estruturaKey].campoPrecoAtual;
    var valor = params[campo];
    return typeof valor === "number" && !isNaN(valor) && valor > 0 ? valor : null;
  }

  // Centro da faixa simulada: usa o preco atual informado quando
  // existe; sem ele (trava_alta/trava_baixa sem o campo opcional
  // preenchido), usa a media dos strikes da estrutura - nunca um
  // numero fixo arbitrario.
  function precoCentralPadrao(estruturaKey, params) {
    var precoAtual = precoAtualDeParams(estruturaKey, params);
    if (precoAtual) return precoAtual;
    var idsDeStrike = { k1: true, k2: true, k: true, kPut: true, kCall: true };
    var strikes = [];
    ESTRUTURAS[estruturaKey].campos.forEach(function (campo) {
      if (idsDeStrike[campo.id] && typeof params[campo.id] === "number" && !isNaN(params[campo.id])) {
        strikes.push(params[campo.id]);
      }
    });
    if (!strikes.length) return 100;
    return strikes.reduce(function (a, b) { return a + b; }, 0) / strikes.length;
  }

  // ---------------------------------------------------------------------
  // Calcula a serie de payoff numa faixa de precos e deriva as
  // metricas (lucro/perda maxima, pontos de equilibrio) POR
  // INTERPOLACAO NUMERICA em vez de formula fechada por estrutura -
  // mais simples e robusto (uma unica logica pra qualquer payoff
  // piecewise-linear), sem risco de erro na derivacao algebrica caso
  // a caso.
  // ---------------------------------------------------------------------
  function calcularSerie(estruturaKey, params, precoCentral) {
    var estrutura = ESTRUTURAS[estruturaKey];
    var faixaMin = Math.max(0, precoCentral * 0.5);
    var faixaMax = precoCentral * 1.5;
    var passos = 200;
    var pontos = [];
    for (var i = 0; i <= passos; i++) {
      var S = faixaMin + (faixaMax - faixaMin) * (i / passos);
      pontos.push({ preco: S, resultado: estrutura.payoff(S, params) });
    }
    return pontos;
  }

  function encontrarPontosDeEquilibrio(pontos) {
    var equilibrios = [];
    for (var i = 1; i < pontos.length; i++) {
      var a = pontos[i - 1];
      var b = pontos[i];
      if ((a.resultado <= 0 && b.resultado > 0) || (a.resultado >= 0 && b.resultado < 0)) {
        // Interpolacao linear entre os 2 pontos pra achar o preco exato onde resultado = 0
        var t = a.resultado === b.resultado ? 0 : -a.resultado / (b.resultado - a.resultado);
        equilibrios.push(a.preco + (b.preco - a.preco) * t);
      }
    }
    return equilibrios;
  }

  function calcularMetricas(pontos) {
    var resultados = pontos.map(function (p) { return p.resultado; });
    var maxResultado = Math.max.apply(null, resultados);
    var minResultado = Math.min.apply(null, resultados);

    // Se o resultado no extremo da faixa simulada ainda esta subindo/caindo
    // de forma continua (nao achatou), o ganho/perda e ilimitado em teoria
    // (ex: Put Protetora sem teto de alta) - marcado como tal em vez de
    // mostrar um numero que so vale pra faixa simulada.
    var n = pontos.length;
    var inclinacaoFinal = pontos[n - 1].resultado - pontos[n - 2].resultado;
    var inclinacaoInicial = pontos[1].resultado - pontos[0].resultado;

    return {
      lucroMaximo: maxResultado,
      lucroIlimitado: inclinacaoFinal > 0.01,
      perdaMaxima: minResultado,
      perdaIlimitada: inclinacaoInicial < -0.01,
      pontosDeEquilibrio: encontrarPontosDeEquilibrio(pontos),
    };
  }

  // ---------------------------------------------------------------------
  // Calendario de vencimentos - regra padrao do ciclo mensal de opcoes
  // na B3 (3a sexta-feira do mes). Excecoes existem (feriado empurra a
  // data, alguns contratos tem ciclo diferente) - por isso o disclaimer
  // explicito na tela, nunca apresentado como data oficial confirmada.
  // ---------------------------------------------------------------------
  function terceiraSextaFeira(ano, mesIndiceZero) {
    var data = new Date(ano, mesIndiceZero, 1);
    var diaSemana = data.getDay(); // 0=domingo ... 5=sexta
    var diasAteSexta = (5 - diaSemana + 7) % 7;
    var primeiraSexta = 1 + diasAteSexta;
    var terceiraSexta = primeiraSexta + 14;
    return new Date(ano, mesIndiceZero, terceiraSexta);
  }

  function proximosVencimentos(quantidade) {
    var hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    var vencimentos = [];
    var mes = hoje.getMonth();
    var ano = hoje.getFullYear();
    var protecaoLoop = 0;
    while (vencimentos.length < quantidade && protecaoLoop < 60) {
      var data = terceiraSextaFeira(ano, mes);
      if (data >= hoje) vencimentos.push(data);
      mes++;
      if (mes > 11) { mes = 0; ano++; }
      protecaoLoop++;
    }
    return vencimentos;
  }

  // ---------------------------------------------------------------------
  // Grafico de payoff (SVG inline, sem biblioteca externa - projeto
  // sem build step). 1 unica serie (o resultado da estrutura no
  // vencimento) - preenchimento verde/vermelho SEMPRE acompanhado de
  // rotulo em texto ("Lucro"/"Perda"), nunca so a cor (acessibilidade,
  // mesma regra ja aplicada no resto do site).
  // ---------------------------------------------------------------------
  function formatarMoeda(valor) {
    return "R$ " + valor.toFixed(2).replace(".", ",");
  }

  function construirSVGPayoff(pontos, metricas, precoAtual) {
    var largura = 760, altura = 320;
    var padEsq = 64, padDir = 20, padTopo = 24, padBaixo = 36;
    var plotLargura = largura - padEsq - padDir;
    var plotAltura = altura - padTopo - padBaixo;

    var precos = pontos.map(function (p) { return p.preco; });
    var resultados = pontos.map(function (p) { return p.resultado; });
    var precoMin = Math.min.apply(null, precos);
    var precoMax = Math.max.apply(null, precos);
    var resultadoMin = Math.min.apply(null, resultados);
    var resultadoMax = Math.max.apply(null, resultados);
    // Margem de 15% no eixo Y pra linha nunca colar na borda do grafico.
    var margemY = Math.max((resultadoMax - resultadoMin) * 0.15, 0.5);
    var yMin = resultadoMin - margemY;
    var yMax = resultadoMax + margemY;

    function x(preco) {
      return padEsq + ((preco - precoMin) / (precoMax - precoMin)) * plotLargura;
    }
    function y(resultado) {
      return padTopo + ((yMax - resultado) / (yMax - yMin)) * plotAltura;
    }

    var zeroY = y(0);

    var linhaPontos = pontos.map(function (p) { return x(p.preco) + "," + y(p.resultado); }).join(" ");

    // Preenchimento de lucro: acompanha a linha real onde resultado>0,
    // "achata" na linha do zero onde resultado<=0 (ver explicacao no
    // corpo do arquivo - min()/max() fazem o clamp certo em coordenada
    // de tela, onde y cresce pra baixo).
    var areaLucroPontos = pontos.map(function (p) { return x(p.preco) + "," + Math.min(y(p.resultado), zeroY); }).join(" ");
    var areaPerdaPontos = pontos.map(function (p) { return x(p.preco) + "," + Math.max(y(p.resultado), zeroY); }).join(" ");
    var xInicio = x(precoMin), xFim = x(precoMax);

    var svg = '<svg viewBox="0 0 ' + largura + " " + altura + '" role="img" aria-label="Gráfico de payoff no vencimento">';

    // Linha de grade horizontal no zero (mais forte - referencia central)
    svg += '<line x1="' + padEsq + '" y1="' + zeroY + '" x2="' + (largura - padDir) + '" y2="' + zeroY + '" stroke="var(--line-strong)" stroke-width="1.5"/>';
    svg += '<text x="' + (padEsq - 8) + '" y="' + (zeroY + 4) + '" text-anchor="end" font-size="11" fill="var(--slate-dim)">R$ 0</text>';

    // Areas de lucro/perda (preenchimento + rotulo em texto, nunca so cor)
    svg += '<polygon points="' + xInicio + "," + zeroY + " " + areaLucroPontos + " " + xFim + "," + zeroY + '" fill="var(--up)" opacity="0.16"/>';
    svg += '<polygon points="' + xInicio + "," + zeroY + " " + areaPerdaPontos + " " + xFim + "," + zeroY + '" fill="var(--down)" opacity="0.16"/>';

    // Linha do resultado
    svg += '<polyline points="' + linhaPontos + '" fill="none" stroke="var(--cream)" stroke-width="2"/>';

    // Marcador do preco atual do ativo
    if (precoAtual !== null && precoAtual !== undefined && precoAtual >= precoMin && precoAtual <= precoMax) {
      var xAtual = x(precoAtual);
      svg += '<line x1="' + xAtual + '" y1="' + padTopo + '" x2="' + xAtual + '" y2="' + (altura - padBaixo) + '" stroke="var(--gold)" stroke-width="1.5" stroke-dasharray="4,3"/>';
      svg += '<text x="' + xAtual + '" y="' + (padTopo - 8) + '" text-anchor="middle" font-size="11" fill="var(--gold)">Preço atual</text>';
    }

    // Marcadores dos pontos de equilibrio
    metricas.pontosDeEquilibrio.forEach(function (be) {
      if (be < precoMin || be > precoMax) return;
      var xBe = x(be);
      svg += '<circle cx="' + xBe + '" cy="' + zeroY + '" r="4" fill="var(--navy-deep)" stroke="var(--cream)" stroke-width="1.5"/>';
      svg += '<text x="' + xBe + '" y="' + (zeroY + 18) + '" text-anchor="middle" font-size="10" fill="var(--slate)">' + formatarMoeda(be) + "</text>";
    });

    // Eixo X - 5 marcacoes de preco
    for (var i = 0; i <= 4; i++) {
      var preco = precoMin + ((precoMax - precoMin) * i) / 4;
      var xPos = x(preco);
      svg += '<text x="' + xPos + '" y="' + (altura - padBaixo + 18) + '" text-anchor="middle" font-size="10" fill="var(--slate-dim)">' + formatarMoeda(preco) + "</text>";
    }

    svg += "</svg>";
    return svg;
  }

  window.AntesDoSinoDerivativos = {
    ESTRUTURAS: ESTRUTURAS,
    calcularSerie: calcularSerie,
    calcularMetricas: calcularMetricas,
    proximosVencimentos: proximosVencimentos,
    terceiraSextaFeira: terceiraSextaFeira,
    construirSVGPayoff: construirSVGPayoff,
    formatarMoeda: formatarMoeda,
    precoAtualDeParams: precoAtualDeParams,
    precoCentralPadrao: precoCentralPadrao,
  };
})();
