# OpenCFD v2606 output-format probe

Image: `opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb`

Retained run: `/Users/bhupeshcholake/Desktop/Claude Codes/physicore drone/.backend/output-format-probe/fc96f428468b49e6ba1bbbc94e6158f2`

Five iterations verify format support only.

Raw plane, line and streamLine outputs contain finite numeric text.

`5/wallShearStress` exists; fields use ASCII with compression off.

## Actual output paths and literal headers

### `postProcessing/solverInfo1/0/solverInfo.dat`

```text
# Solver information
# Time        	U_solver      	Ux_initial    	Ux_final      	Ux_iters      	Uy_initial    	Uy_final      	Uy_iters      	Uz_initial    	Uz_final      	Uz_iters      	U_converged   	p_solver      	p_initial     	p_final       	p_iters       	p_converged   
```

### `postProcessing/cuttingPlane/5/p_yNormal.raw`

```text
# p  POINT_DATA 8481
# x y z  p
```

### `postProcessing/cuttingPlane/5/U_yNormal.raw`

```text
# U  POINT_DATA 8481
# x y z  U_x U_y U_z
```

### `postProcessing/sample1/5/centreLine_p_U.xy`

```text
```

### `postProcessing/sets/streamLines/5/k_track0.raw`

```text
# k  X_DATA 28095
# x  k
```

### `postProcessing/sets/streamLines/5/U_track0.raw`

```text
# U  X_DATA 28095
# x  U_x U_y U_z
```

### `postProcessing/sets/streamLines/5/p_track0.raw`

```text
# p  X_DATA 28095
# x  p
```

### `postProcessing/wallShearStress/0/wallShearStress.dat`

```text
# Wall shear stress
# Time        	patch         	min           	max           
```

### `postProcessing/forceCoeffs1/0/coefficient.dat`

```text
# Force and moment coefficients
# dragDir     : (1.000000e+00 0.000000e+00 0.000000e+00)
# sideDir     : (0.000000e+00 1.000000e+00 0.000000e+00)
# liftDir     : (0.000000e+00 0.000000e+00 1.000000e+00)
# rollAxis    : (1.000000e+00 0.000000e+00 0.000000e+00)
# pitchAxis   : (0.000000e+00 1.000000e+00 0.000000e+00)
# yawAxis     : (0.000000e+00 0.000000e+00 1.000000e+00)
# magUInf     : 2.000000e+01
# lRef        : 1.420000e+00
# Aref        : 7.500000e-01
# CofR        : (7.200000e-01 0.000000e+00 0.000000e+00)
#
# Time        	Cd            	Cd(f)         	Cd(r)         	Cl            	Cl(f)         	Cl(r)         	CmPitch       	CmRoll        	CmYaw         	Cs            	Cs(f)         	Cs(r)         
```

### `postProcessing/forces/0/force.dat`

```text
# Force       
# CofR        : (4.974613e-01 -1.671896e-02 1.250000e-01)
#
# Time        	total_x total_y total_z	pressure_x pressure_y pressure_z	viscous_x viscous_y viscous_z
```

### `postProcessing/forces/0/moment.dat`

```text
# Moment      
# CofR        : (4.974613e-01 -1.671896e-02 1.250000e-01)
#
# Time        	total_x total_y total_z	pressure_x pressure_y pressure_z	viscous_x viscous_y viscous_z
```

## Vendor input hashes

```json
{
  "incompressible/simpleFoam/motorBike/system/cuttingPlane": "2177d56457fc0b58a4cfab48eaf054dbf082f6b28fde634d7a7a354477a8d132",
  "incompressible/simpleFoam/motorBike/system/streamLines": "0c520a48ee7e553472c92dfe69119a64bda16d6b11f45d5d629966e539f8bd4f",
  "incompressible/simpleFoam/motorBike/system/forceCoeffs": "6f516ecef3d09456ef42c5fb297d118373927b8e35a518e0059499fe42cf1fc5",
  "incompressible/pimpleFoam/RAS/wingMotion/wingMotion2D_simpleFoam/system/forces": "8d5bc4a6fd701b664b2bd79c95ff490817c36836a284ab0226b2bdf1efb6e77e",
  "incompressible/simpleFoam/motorBike/system/solverInfo": "2cefb568aafc92b88a08cce69b63866d5dd57c6cb7ac0165545f7c431629fe0d",
  "incompressible/simpleFoam/rotatingCylinders/system/controlDict": "6e964c685c3fd0614240e84ea640082409033dee52e94eb1b06773f842a779dc",
  "incompressible/simpleFoam/bump2D/setups.orig/common/system/controlDict": "7071abb478334042306c16f399c463bc96a58fb7454e91479f3bdcff2ce49bdb",
  "incompressible/simpleFoam/squareBend/system/controlDict": "609ce28b34b60ff83612a329cd58f4653d6ba1944a6fc7f775d2111681725f10"
}
```
