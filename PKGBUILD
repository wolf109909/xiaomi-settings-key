# Maintainer: reverse-engineered for Xiaomi Book 14 Pro 2026
pkgname=xiaomi-settings-key
pkgver=1.0.0
pkgrel=2
pkgdesc="Userspace handler for the Xiaomi Book 14 Pro 2026 dedicated settings key (runs a configurable command on press)"
arch=('any')
license=('GPL-2.0-or-later')
depends=('python' 'systemd')
optdepends=('konsole: default command')
backup=('etc/xiaomi-settings-key/command.sh')
source=("xiaomi-settings-keyd.py"
        "xiaomi-settings-key.service"
        "99-xiaomi-settings-key.rules"
        "command.sh")
sha256sums=('SKIP' 'SKIP' 'SKIP' 'SKIP')

package() {
    install -Dm755 xiaomi-settings-keyd.py "$pkgdir/usr/bin/xiaomi-settings-keyd"
    install -Dm644 xiaomi-settings-key.service \
        "$pkgdir/usr/lib/systemd/system/xiaomi-settings-key.service"
    install -Dm644 99-xiaomi-settings-key.rules \
        "$pkgdir/usr/lib/udev/rules.d/99-xiaomi-settings-key.rules"
    install -Dm755 command.sh "$pkgdir/etc/xiaomi-settings-key/command.sh"
}
