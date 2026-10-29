"""Fujifilm X-T30 model definition."""

from .base import CameraModel


class XT30Model(CameraModel):
    """Fujifilm X-T30 camera model (X-Processor 4 / X-Trans IV)."""

    def __init__(self):
        super().__init__(
            id="xt30",
            name="Fujifilm X-T30",
            model_code_prefix="0005553",
            processor="X-Processor 4",
            sensor="26.1MP X-Trans CMOS IV (APS-C)",
            latest_fw="2.01",
            fw_filename="FWUP0020.DAT",
            dl_url="https://dl.fujifilm-x.com/support/firmware/x-t30-201-jm7f4emq/FWUP0020.DAT",
            virtual_delta=0x0135FFB8,
            known_offsets={
                "FSIM_CLASSIC_NEG": 0x00000000,
                "FSIM_ETERNA": 0x00000000,
            },
        )


XT30_MODEL = XT30Model()
