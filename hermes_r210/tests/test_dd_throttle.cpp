// Testa o freio de risco por rebaixamento do Caso 6 (funcao pura, isolada do
// motor de entrada/saida). Nao e simulacao de mercado.
#include <cmath>
#include <cassert>
#include <iostream>
bool MathIsValidNumber(double x){return std::isfinite(x);}
#include "../src/DDThrottleCore.mqh"

int main(){
 const double band1=15.0, mult1=0.50, band2=25.0, mult2=0.25;

 // 1. Sem rebaixamento (patrimonio no pico, ou acima dele): risco cheio.
 assert(DDThrottleMultiplier(10000,10000,band1,mult1,band2,mult2)==1.0);
 assert(DDThrottleMultiplier(10500,10000,band1,mult1,band2,mult2)==1.0);

 // 2. Limiar da banda 1: inclusive (exatamente 15% de DD -> ainda risco cheio).
 assert(DDThrottleMultiplier(8500,10000,band1,mult1,band2,mult2)==1.0);      // DD=15.00%
 assert(DDThrottleMultiplier(8499,10000,band1,mult1,band2,mult2)==mult1);    // DD=15.01%

 // 3. Limiar da banda 2: inclusive (exatamente 25% de DD -> ainda multiplicador 1).
 assert(DDThrottleMultiplier(7500,10000,band1,mult1,band2,mult2)==mult1);    // DD=25.00%
 assert(DDThrottleMultiplier(7499,10000,band1,mult1,band2,mult2)==mult2);    // DD=25.01%

 // 4. Rebaixamento profundo: nunca some (para no multiplicador 2, nao zera).
 assert(DDThrottleMultiplier(1000,10000,band1,mult1,band2,mult2)==mult2);    // DD=90%

 // 5. Dados invalidos -> 0 (chao de seguranca; nunca amplia risco por engano).
 assert(DDThrottleMultiplier(0,10000,band1,mult1,band2,mult2)==0);
 assert(DDThrottleMultiplier(-100,10000,band1,mult1,band2,mult2)==0);
 assert(DDThrottleMultiplier(9000,0,band1,mult1,band2,mult2)==0);
 assert(DDThrottleMultiplier(9000,-100,band1,mult1,band2,mult2)==0);
 assert(DDThrottleMultiplier(std::nan(""),10000,band1,mult1,band2,mult2)==0);
 assert(DDThrottleMultiplier(9000,std::nan(""),band1,mult1,band2,mult2)==0);

 // 6. Configuracao invalida (bandas fora de ordem, multiplicadores fora de
 // faixa ou crescentes com o rebaixamento) -> 0, mesmo com equity/pico validos.
 assert(DDThrottleMultiplier(9000,10000,-1,mult1,band2,mult2)==0);        // banda1 negativa
 assert(DDThrottleMultiplier(9000,10000,band1,mult1,band1,mult2)==0);     // banda2 <= banda1
 assert(DDThrottleMultiplier(9000,10000,band1,0,band2,mult2)==0);         // mult1 <= 0
 assert(DDThrottleMultiplier(9000,10000,band1,1.5,band2,mult2)==0);       // mult1 > 1
 assert(DDThrottleMultiplier(9000,10000,band1,mult1,band2,0)==0);         // mult2 <= 0
 assert(DDThrottleMultiplier(9000,10000,band1,mult1,band2,mult1+0.1)==0); // mult2 > mult1

 std::cout<<"DD Throttle (Caso 6): sem rebaixamento, limiares inclusivos das duas bandas, "
            "profundidade maxima, dados invalidos e configuracao invalida passaram.\n";
 return 0;
}
