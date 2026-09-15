// Testa o saque de lucro do Caso 7 (funcoes puras, isoladas do motor de
// entrada/saida). Nao e simulacao de mercado.
#include <cmath>
#include <cassert>
#include <algorithm>
#include <iostream>
template<class A,class B> double MathMax(A a,B b){return std::max(double(a),double(b));}
bool MathIsValidNumber(double x){return std::isfinite(x);}
#include "../src/WithdrawalCore.mqh"

int main(){
 // 1. WDUpdate: sem novo recorde -> nada muda.
 { WDState st{10000,0};
   WDUpdate(10000,0.5,st); assert(st.realizedPeak==10000 && st.bankedWithdrawn==0);
   WDUpdate(9000,0.5,st);  assert(st.realizedPeak==10000 && st.bankedWithdrawn==0); // saldo caiu, nao desfaz nada
 }
 // 2. Novo recorde: divide o incremento pela fracao (50%).
 { WDState st{10000,0};
   WDUpdate(12000,0.5,st); // incremento de 2000 -> 1000 sacado, pico vira 12000
   assert(st.realizedPeak==12000 && std::abs(st.bankedWithdrawn-1000)<1e-9);
 }
 // 3. Multiplos recordes acumulam o total sacado.
 { WDState st{10000,0};
   WDUpdate(12000,0.5,st); // +2000 -> saca 1000, pico 12000, banked 1000
   WDUpdate(11000,0.5,st); // abaixo do pico -> nada muda
   WDUpdate(16000,0.5,st); // +4000 sobre o pico -> saca +2000, pico 16000, banked 3000
   assert(st.realizedPeak==16000 && std::abs(st.bankedWithdrawn-3000)<1e-9);
 }
 // 4. Fracoes-limite: 0 (nunca saca, degenera pro Caso 4) e 1 (saca tudo, capital nunca cresce).
 { WDState st{10000,0};
   WDUpdate(15000,0.0,st); assert(st.realizedPeak==15000 && st.bankedWithdrawn==0);
 }
 { WDState st{10000,0};
   WDUpdate(15000,1.0,st); assert(st.realizedPeak==15000 && std::abs(st.bankedWithdrawn-5000)<1e-9);
 }
 // 5. Dados/config invalidos -> nao atualiza nada (chao de seguranca).
 { WDState st{10000,0};
   WDUpdate(std::nan(""),0.5,st); assert(st.realizedPeak==10000 && st.bankedWithdrawn==0);
   WDUpdate(15000,-0.01,st);      assert(st.realizedPeak==10000 && st.bankedWithdrawn==0);
   WDUpdate(15000,1.01,st);       assert(st.realizedPeak==10000 && st.bankedWithdrawn==0);
   WDUpdate(15000,std::nan(""),st); assert(st.realizedPeak==10000 && st.bankedWithdrawn==0);
 }
 // 6. WDTradingCapital: subtracao simples, piso em 0, dados invalidos -> 0.
 assert(std::abs(WDTradingCapital(50000,20000)-30000)<1e-9);
 assert(WDTradingCapital(15000,20000)==0);      // sacado > patrimonio atual (rebaixamento) -> nunca negativo
 assert(WDTradingCapital(std::nan(""),1000)==0);
 assert(WDTradingCapital(50000,std::nan(""))==0);

 std::cout<<"Saque de lucro (Caso 7): sem novo recorde, split correto, acumulo em multiplos "
            "recordes, fracoes-limite 0/1, dados/config invalidos e piso em zero passaram.\n";
 return 0;
}
