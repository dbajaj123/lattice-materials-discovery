"""Exercise installed Kawin APIs before integrating the evaluator."""
import os
os.environ.setdefault('MPLCONFIGDIR', '/tmp/materials-discovery-mpl')
import numpy as np
from kawin.thermo import BinaryThermodynamics
from kawin.precipitation import MatrixParameters, PrecipitateParameters, PrecipitateModel
from kawin.precipitation.coupling import (
    StrengthModel, DislocationParameters, CoherencyContribution,
    ModulusContribution, APBContribution, InterfacialContribution,
)

therm = BinaryThermodynamics('vendor/kawin/examples/AlScZr.tdb', ['AL', 'SC'], ['FCC_A1', 'AL3SC'])
therm.setGuessComposition(0.24)
therm.setDiffusivity(lambda T: 1.9e-4*np.exp(-164000/(8.314*T)), 'FCC_A1')
matrix = MatrixParameters(['SC'])
matrix.initComposition = 0.002
matrix.volume.setVolume((0.409e-9)**3, 'VA', 4)
prec = PrecipitateParameters('AL3SC')
prec.gamma = 0.1
prec.volume.setVolume((0.4196e-9)**3, 'VA', 4)
prec.nucleation.setNucleationType('bulk')
strength = StrengthModel(prec, [CoherencyContribution(eps=2/3*0.0125), ModulusContribution(Gp=67.9e9), APBContribution(yAPB=0.5), InterfacialContribution(gamma=0.1)], DislocationParameters(G=25.4e9, b=0.286e-9, nu=0.34))
model = PrecipitateModel(matrix, prec, therm, 673.15)
model.addCouplingModel(strength)
model.solve(3600, verbose=True, vIt=5000)
print('DATA', {k: np.shape(v) for k,v in vars(model.data).items()})
print('RESULT', model.data.time[-1], model.data.Ravg[-1], model.data.volFrac[-1], strength.totalStrength(model)[-1])
print('PBM', model.PBM[0].PSD.shape)
