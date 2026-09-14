#ifndef HERMES_DD_THROTTLE_CORE_210
#define HERMES_DD_THROTTLE_CORE_210
// Caso 6 - freio de risco por rebaixamento (drawdown throttle).
//
// Motivacao: no Caso 4, subir o risco% aumenta o lucro muito mais rapido do
// que aumenta a dor (2%->5% e so 2.5x de risco mas ~14.6x de lucro no sweep
// testado) - mas o Fator de Recuperacao piora a cada degrau (3.87->1.51),
// porque sizing por % do patrimonio compoe geometricamente nos dois sentidos.
// Nao existe ajuste dentro da formula do Caso 4 que quebre esse acoplamento;
// este e um mecanismo DIFERENTE, isolado como Caso 6, comparado contra o
// Caso 4 no mesmo risco-base, nunca substituindo-o.
//
// Ideia: reduzir o risco% EFETIVO quando o patrimonio esta em rebaixamento
// contra o maior pico ja visto, e restaurar o risco cheio assim que um novo
// pico e feito. So muda o VOLUME; nenhuma entrada/saida e alterada.
//
// Funcao pura: (patrimonio atual, pico ja visto, duas bandas de rebaixamento
// e seus multiplicadores) -> multiplicador em (0,1] a aplicar sobre o risco%
// normal. Dados invalidos ou configuracao invalida (bandas fora de ordem,
// multiplicadores fora de (0,1] ou nao-decrescentes) devolvem 0 - o chao de
// seguranca e nao operar, nunca ampliar risco por engano de configuracao.
double DDThrottleMultiplier(const double equity, const double peakEquity,
                            const double band1Pct, const double mult1,
                            const double band2Pct, const double mult2)
{
   if (!MathIsValidNumber(equity) || !MathIsValidNumber(peakEquity) || equity <= 0 || peakEquity <= 0)
      return 0;
   if (!MathIsValidNumber(band1Pct) || !MathIsValidNumber(band2Pct) ||
       !MathIsValidNumber(mult1) || !MathIsValidNumber(mult2) ||
       band1Pct < 0 || band2Pct <= band1Pct ||
       mult1 <= 0 || mult1 > 1.0 || mult2 <= 0 || mult2 > mult1)
      return 0;
   if (equity >= peakEquity) return 1.0;
   double ddPct = 100.0 * (peakEquity - equity) / peakEquity;
   if (ddPct <= band1Pct) return 1.0;
   if (ddPct <= band2Pct) return mult1;
   return mult2;
}
#endif
