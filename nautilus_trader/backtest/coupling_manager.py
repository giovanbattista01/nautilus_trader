"""

Custom Sirius module to handle italian zones coupling logic

"""

from dataclasses import dataclass

@dataclass(frozen=True)
class CouplingInterval:
    start_ns: int                        # coupling begins (UNIX nanos)
    end_ns: int                          # coupling ends   (UNIX nanos)
    instrument_ids: frozenset[str]       # group of coupled instrument IDs
    factor: float = 1.0                  # 1.0 = full propagation, 0.5 = 50%, etc.

class ZoneCouplingManager:
    def __init__(self, coupling_intervals: list[CouplingInterval], log=None):
        self._schedule = sorted(coupling_intervals, key=lambda x: x.start_ns)

        self._index: dict[str, list[CouplingInterval]] = {}
        self._engines = {}
        self._log = log
        for interval in self._schedule:
            for iid in interval.instrument_ids:
                self._index.setdefault(iid, []).append(interval)

    def get_engines(self):
        return self._engines

    def set_engines(self, engines:dict): # order matching engines keyed by instrument_id
        self._engines = engines

    def propagate_liq_consumption(self, instrument_id, ts_ns, side, price_raw, qty_raw):
        """ Write consumption into other siblings' engines"""

        for interval in self._index.get(instrument_id,[]):
            if interval.start_ns <= ts_ns < interval.end_ns:

                siblings = [instr_id for instr_id in interval.instrument_ids if instr_id != instrument_id]
                
                if self._log is not None and siblings:
                    self._log.info(
                        f"COUPLING_PROP ts={ts_ns} src={instrument_id} siblings={siblings} px={price_raw} qty={qty_raw} factor={interval.factor}"
                    )

                for sibling_id in siblings:
                    engine = self._engines.get(sibling_id)
                    if engine is None:
                        if self._log is not None:
                            self._log.warning(f"No engine found for sibling {sibling_id}, skipping propagation")
                        continue
                    propagated = int(qty_raw * interval.factor)
                    if propagated == 0:
                        if self._log is not None:
                            self._log.warning(
                                f"Propagated quantity is zero for sibling {sibling_id} with factor {interval.factor}, skipping propagation"
                            )
                        continue
                    cons = engine.get_ask_consumption() if side == 1 else engine.get_bid_consumption() # 1 = BUY, 2=SELL
                    state = cons.get(price_raw)
                    if state is None:
                        cons[price_raw] = (propagated, propagated)
                    else:
                        cons[price_raw] = (state[0], state[1] + propagated)

                    if self._log is not None:
                        self._log.info(f"Propagated {propagated} units from {instrument_id} to {sibling_id} at price {price_raw}")

                return siblings
            
        return []
